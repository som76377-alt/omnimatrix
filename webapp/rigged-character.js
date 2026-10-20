(function (root, factory) {
  "use strict";
  const rig = factory();
  if (typeof module === "object" && module.exports) module.exports = rig;
  if (root) root.OmnitrixRig = rig;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TAU = Math.PI * 2;
  const PROFILES = Object.freeze({
    idle:  { cyclesPerSecond: 0.18 },
    wave:  { cyclesPerSecond: 0.72 },
    walk:  { cyclesPerSecond: 0.48 },
    run:   { cyclesPerSecond: 0.95 },
    dance: { cyclesPerSecond: 0.62 },
    jump:  { cyclesPerSecond: 0.48 },
    nod:   { cyclesPerSecond: 0.45 }
  });

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function detectAction(brief) {
    const text = String(brief || "").toLowerCase();
    if (/\b(wav(?:e|es|ing)|greet(?:s|ing)?|hello|hi)\b/.test(text)) return "wave";
    if (/\b(run(?:s|ning)?|sprint(?:s|ing)?|jog(?:s|ging)?)\b/.test(text)) return "run";
    if (/\b(walk(?:s|ing)?|march(?:es|ing)?)\b/.test(text)) return "walk";
    if (/\bdanc(?:e|es|ing)\b/.test(text)) return "dance";
    if (/\b(jump(?:s|ing)?|leap(?:s|ing)?)\b/.test(text)) return "jump";
    if (/\b(nod(?:s|ding)?|yes)\b/.test(text)) return "nod";
    return "idle";
  }

  // Smoothly interpolates [normalized time, value] pairs. Each segment uses
  // smoothstep easing, avoiding abrupt velocity changes at authored keyframes.
  function sampleCurve(keys, progress) {
    if (!Array.isArray(keys) || keys.length === 0) return 0;
    if (progress <= keys[0][0]) return keys[0][1];
    if (progress >= keys[keys.length - 1][0]) return keys[keys.length - 1][1];
    for (let index = 0; index < keys.length - 1; index += 1) {
      const from = keys[index], to = keys[index + 1];
      if (progress < from[0] || progress > to[0]) continue;
      const span = Math.max(1e-9, to[0] - from[0]);
      const raw = clamp((progress - from[0]) / span, 0, 1);
      const eased = raw * raw * (3 - 2 * raw);
      return from[1] + (to[1] - from[1]) * eased;
    }
    return keys[keys.length - 1][1];
  }

  // Time is sampled in seconds rather than frame count, so playback and WebM
  // rendering share the same deterministic movement at 24, 30, or 60 fps.
  function samplePose(brief, elapsed, duration) {
    const action = detectAction(brief);
    const profile = PROFILES[action] || PROFILES.idle;
    const rawTime = Number(elapsed);
    const t = Number.isFinite(rawTime) ? Math.max(0, rawTime) : 0;
    const rawDuration = Number(duration);
    const span = Number.isFinite(rawDuration) ? Math.max(0.1, rawDuration || 0.1) : 0.1;
    const progress = clamp(t / span, 0, 1);
    const phase = t * profile.cyclesPerSecond * TAU;
    const swing = Math.sin(phase);
    const opposite = -swing;
    const wave = action === "wave";
    const run = action === "run";
    const walk = action === "walk";
    const dance = action === "dance";
    const jump = action === "jump";
    const nod = action === "nod";
    const stride = walk ? 0.46 : run ? 0.76 : dance ? 0.48 : 0;
    const cycleProgress = (phase / TAU) % 1;
    const jumpPulse = sampleCurve([[0, 0], [0.18, 0.32], [0.42, 1], [0.67, 0.4], [1, 0]], cycleProgress);
    const lift = jump ? jumpPulse * 22 : run ? Math.abs(swing) * 4 : Math.sin(t * 2.3) * 2;
    const lean = run ? 0.14 : walk ? 0.04 : dance ? Math.sin(phase * 0.5) * 0.1 : 0;
    let leftUpperArmAngle, leftForearmAngle, rightUpperArmAngle, rightForearmAngle;
    if (wave) {
      leftUpperArmAngle = -0.56;
      leftForearmAngle = -0.18;
      rightUpperArmAngle = 2.55 + swing * 0.1;
      rightForearmAngle = 2.72 + Math.sin(t * TAU * 1.45) * 0.42;
    } else if (walk || run) {
      leftUpperArmAngle = -0.22 - swing * stride * 0.85;
      leftForearmAngle = -0.1 - swing * stride * 0.45;
      rightUpperArmAngle = 0.22 + swing * stride * 0.85;
      rightForearmAngle = 0.1 + swing * stride * 0.45;
    } else if (dance) {
      leftUpperArmAngle = -1.55 + Math.sin(phase) * 0.25;
      leftForearmAngle = -2.25 + Math.sin(phase + 1) * 0.24;
      rightUpperArmAngle = 1.65 + Math.sin(phase + 0.8) * 0.25;
      rightForearmAngle = 2.15 + Math.sin(phase + 1.7) * 0.24;
    } else if (jump) {
      leftUpperArmAngle = -1.25;
      leftForearmAngle = -1.95;
      rightUpperArmAngle = 1.25;
      rightForearmAngle = 1.95;
    } else {
      leftUpperArmAngle = -0.18 + Math.sin(phase) * 0.04;
      leftForearmAngle = -0.08;
      rightUpperArmAngle = 0.18 + Math.sin(phase + Math.PI) * 0.04;
      rightForearmAngle = 0.08;
    }
    return {
      action, t, duration: span, progress, phase, swing, opposite,
      wave, run, walk, dance, jump, nod, stride,
      lift, lean,
      xPosition: (walk || run) ? 0.48 + Math.sin(t * 0.9) * 0.018 : 0.49,
      headBob: nod ? Math.sin(phase) * 3 : Math.sin(t * 1.2) * 0.6,
      headTilt: dance ? Math.sin(phase * 0.5) * 0.1 : 0,
      leftLegAngle: 0.05 + swing * stride,
      rightLegAngle: -0.05 + opposite * stride,
      leftAnkleAngle: (0.05 + swing * stride) * 0.35 - Math.max(0, swing) * stride * 0.22,
      rightAnkleAngle: (-0.05 + opposite * stride) * 0.35 - Math.max(0, opposite) * stride * 0.22,
      leftUpperArmAngle, leftForearmAngle, rightUpperArmAngle, rightForearmAngle,
      waveHandOffset: wave ? Math.sin(t * TAU * 1.45 + 0.3) * 0.32 : 0
    };
  }

  function child(parent, angle, length, unit) {
    return {
      x: parent.x + Math.sin(angle) * length * unit,
      y: parent.y + Math.cos(angle) * length * unit
    };
  }

  // A two-dimensional parent/child joint hierarchy. Lengths are fixed in
  // character units and scale uniformly with the output canvas.
  function buildSkeleton(options) {
    const ox = Number(options.ox) || 0;
    const oy = Number(options.oy) || 0;
    const unit = Math.max(0.001, Number(options.unit) || 1);
    const pose = options.pose || samplePose("", 0, 1);
    const p = (x, y) => ({ x: ox + x * unit, y: oy + y * unit });
    const leftHip = p(-15, 1), rightHip = p(15, 1);
    const leftShoulder = p(-29, -111), rightShoulder = p(29, -111);
    const neck = p(0, -132);
    const head = p(-pose.lean * 14, -170 - pose.headBob);
    const leftKnee = child(leftHip, pose.leftLegAngle, 58, unit);
    const rightKnee = child(rightHip, pose.rightLegAngle, 58, unit);
    const leftAnkle = child(leftKnee, pose.leftAnkleAngle, 61, unit);
    const rightAnkle = child(rightKnee, pose.rightAnkleAngle, 61, unit);
    const leftElbow = child(leftShoulder, pose.leftUpperArmAngle, 48, unit);
    const leftWrist = child(leftElbow, pose.leftForearmAngle, 45, unit);
    const rightElbow = child(rightShoulder, pose.rightUpperArmAngle, 48, unit);
    const rightWrist = child(rightElbow, pose.rightForearmAngle, 45, unit);
    return {
      root: { x: ox, y: oy },
      leftHip, rightHip, leftShoulder, rightShoulder, neck, head,
      leftKnee, rightKnee, leftAnkle, rightAnkle,
      leftElbow, rightElbow, leftWrist, rightWrist
    };
  }

  return Object.freeze({ detectAction, sampleCurve, samplePose, buildSkeleton });
});
