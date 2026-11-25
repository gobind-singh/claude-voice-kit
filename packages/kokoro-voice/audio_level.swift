// audio-level: is sound actually coming out of these apps right now? (macOS 14.2+)
//
// macOS reports an app's audio channel as "running" while it's open, even when it's silent
// (a Discord tab in Safari, a dictation app, system helpers). This helper listens to the
// output of the given processes for a moment through a Core Audio process tap and prints
// how loud it was. It only measures the level: no audio is stored or sent anywhere.
//
//   audio-level <pid>[,<pid>...] [milliseconds]   → {"ok":true,"peak_db":-62.1,"rms_db":-80.3}
//   audio-level --status                          → {"ok":true,"permission":"granted|denied|unknown"}
//   audio-level --request                         → asks macOS for "System Audio Recording" permission
//
// Needs the "System Audio Recording" permission (Privacy & Security → Screen & System Audio
// Recording). Without it, macOS delivers silence, so --status is checked first.

import AudioToolbox
import CoreAudio
import Foundation

func emit(_ d: [String: Any], code: Int32 = 0) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: d, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
    exit(code)
}

// MARK: permission (TCC, private API, the same one Apple's own tools use)

typealias PreflightFn = @convention(c) (CFString, CFDictionary?) -> Int
typealias RequestFn = @convention(c) (CFString, CFDictionary?, @escaping (Bool) -> Void) -> Void
let tcc = dlopen("/System/Library/PrivateFrameworks/TCC.framework/Versions/A/TCC", RTLD_NOW)
let service = "kTCCServiceAudioCapture" as CFString

func permission() -> String {
    guard let tcc, let sym = dlsym(tcc, "TCCAccessPreflight") else { return "unknown" }
    switch unsafeBitCast(sym, to: PreflightFn.self)(service, nil) {
    case 0: return "granted"
    case 1: return "denied"
    default: return "unknown"
    }
}

func request() -> Bool {
    guard let tcc, let sym = dlsym(tcc, "TCCAccessRequest") else { return false }
    let done = DispatchSemaphore(value: 0)
    var granted = false
    unsafeBitCast(sym, to: RequestFn.self)(service, nil) { ok in granted = ok; done.signal() }
    _ = done.wait(timeout: .now() + 120)
    return granted
}

// MARK: become our own "responsible process"
// Started by another program (the voice service), macOS would ask that program for permission.
// Re-launching ourselves with responsibility disclaimed makes the permission belong to this helper.

typealias DisclaimFn = @convention(c) (UnsafeMutablePointer<posix_spawnattr_t?>, Int32) -> Int32

func relaunchDisclaimed() -> Never {
    var attr: posix_spawnattr_t?
    posix_spawnattr_init(&attr)
    if let sym = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "responsibility_spawnattrs_setdisclaim") {
        _ = unsafeBitCast(sym, to: DisclaimFn.self)(&attr, 1)
    }
    setenv("AUDIO_LEVEL_DISCLAIMED", "1", 1)
    let argv = CommandLine.arguments.map { strdup($0) } + [nil]
    var pid: pid_t = 0
    let rc = posix_spawn(&pid, CommandLine.arguments[0], nil, &attr, argv, environ)
    if rc != 0 { emit(["ok": false, "error": "spawn failed: \(rc)"], code: 1) }
    var status: Int32 = 0
    waitpid(pid, &status, 0)
    exit((status >> 8) & 0xff)
}

// MARK: Core Audio helpers

func getProp<T>(_ obj: AudioObjectID, _ sel: AudioObjectPropertySelector, _ value: inout T,
                qualifier: UnsafeRawPointer? = nil, qualifierSize: UInt32 = 0) -> OSStatus {
    var addr = AudioObjectPropertyAddress(mSelector: sel, mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var size = UInt32(MemoryLayout<T>.size)
    return withUnsafeMutableBytes(of: &value) {
        AudioObjectGetPropertyData(obj, &addr, qualifierSize, qualifier, &size, $0.baseAddress!)
    }
}

func processObject(for pid: pid_t) -> AudioObjectID? {
    var p = pid
    var obj = AudioObjectID(kAudioObjectUnknown)
    let st = withUnsafePointer(to: &p) {
        getProp(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyTranslatePIDToProcessObject, &obj,
                qualifier: $0, qualifierSize: UInt32(MemoryLayout<pid_t>.size))
    }
    return st == noErr && obj != kAudioObjectUnknown ? obj : nil
}

func defaultOutputUID() -> String? {
    var dev = AudioObjectID(kAudioObjectUnknown)
    guard getProp(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultSystemOutputDevice, &dev) == noErr
    else { return nil }
    var uid: Unmanaged<CFString>?
    guard getProp(dev, kAudioDevicePropertyDeviceUID, &uid) == noErr, let uid else { return nil }
    return uid.takeRetainedValue() as String
}

func db(_ v: Double) -> Double { v > 0 ? max(-120, (20 * log10(v) * 10).rounded() / 10) : -120 }

// MARK: main

let args = Array(CommandLine.arguments.dropFirst())
if ProcessInfo.processInfo.environment["AUDIO_LEVEL_DISCLAIMED"] == nil { relaunchDisclaimed() }
if args.first == "--status" { emit(["ok": true, "permission": permission()]) }
if args.first == "--request" { emit(["ok": true, "granted": request()]) }

guard let first = args.first else { emit(["ok": false, "error": "usage: audio-level <pid,...> [ms]"], code: 2) }
let pids = first.split(separator: ",").compactMap { pid_t($0) }
let ms = args.count > 1 ? max(50, min(2000, Int(args[1]) ?? 250)) : 250

if permission() != "granted" { emit(["ok": false, "error": "no permission", "permission": permission()], code: 3) }
let objects = pids.compactMap(processObject)
if objects.isEmpty { emit(["ok": true, "peak_db": -120.0, "rms_db": -120.0, "note": "no audio processes"]) }
guard let outputUID = defaultOutputUID() else { emit(["ok": false, "error": "no output device"], code: 1) }

let tap = CATapDescription(stereoMixdownOfProcesses: objects)
tap.uuid = UUID()
tap.muteBehavior = .unmuted
tap.isPrivate = true
var tapID = AudioObjectID(kAudioObjectUnknown)
var st = AudioHardwareCreateProcessTap(tap, &tapID)
guard st == noErr else { emit(["ok": false, "error": "tap failed: \(st)"], code: 1) }

let aggregate: [String: Any] = [
    kAudioAggregateDeviceNameKey: "voice-kit level check",
    kAudioAggregateDeviceUIDKey: UUID().uuidString,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true, kAudioSubTapUIDKey: tap.uuid.uuidString]],
]
var aggID = AudioObjectID(kAudioObjectUnknown)
st = AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &aggID)
guard st == noErr else {
    AudioHardwareDestroyProcessTap(tapID)
    emit(["ok": false, "error": "aggregate device failed: \(st)"], code: 1)
}

final class Meter: @unchecked Sendable {
    let lock = NSLock()
    var peak: Float = 0, sumSquares = 0.0, count = 0
}
let meter = Meter()
var procID: AudioDeviceIOProcID?
st = AudioDeviceCreateIOProcIDWithBlock(&procID, aggID, nil) { _, input, _, _, _ in
    var peak: Float = 0, sum = 0.0, n = 0
    for buf in UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)) {
        guard let data = buf.mData else { continue }
        let count = Int(buf.mDataByteSize) / MemoryLayout<Float>.size
        let samples = data.bindMemory(to: Float.self, capacity: count)
        for i in 0..<count {
            let v = abs(samples[i])
            if v > peak { peak = v }
            sum += Double(v) * Double(v)
        }
        n += count
    }
    meter.lock.lock()
    meter.peak = max(meter.peak, peak); meter.sumSquares += sum; meter.count += n
    meter.lock.unlock()
}
func cleanup() {
    if let procID { AudioDeviceStop(aggID, procID); AudioDeviceDestroyIOProcID(aggID, procID) }
    AudioHardwareDestroyAggregateDevice(aggID)
    AudioHardwareDestroyProcessTap(tapID)
}
guard st == noErr, AudioDeviceStart(aggID, procID) == noErr else {
    cleanup()
    emit(["ok": false, "error": "start failed: \(st)"], code: 1)
}
Thread.sleep(forTimeInterval: Double(ms) / 1000)
cleanup()

meter.lock.lock()
let rms = meter.count > 0 ? (meter.sumSquares / Double(meter.count)).squareRoot() : 0
emit(["ok": true, "peak_db": db(Double(meter.peak)), "rms_db": db(rms), "samples": meter.count, "ms": ms])
