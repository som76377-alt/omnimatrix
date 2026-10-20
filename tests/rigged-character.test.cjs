"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const rig = require("../webapp/rigged-character.js");

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

test("briefs map to the seven supported deterministic actions", () => {
  const cases = [
    ["A person waves hello", "wave"],
    ["A person walks forward", "walk"],
    ["A person is running", "run"],
    ["A character is dancing", "dance"],
    ["A person jumps", "jump"],
    ["A character nods yes", "nod"],
    ["A character waits calmly", "idle"]
  ];
  for (const [brief, action] of cases) assert.equal(rig.detectAction(brief), action);
});

test("same brief and time always return the same pose", () => {
  const first = rig.samplePose("A person waving hello", 1.375, 8);
  const second = rig.samplePose("A person waving hello", 1.375, 8);
  assert.deepEqual(first, second);
});

test("wave motion moves the forearm and wrist over time", () => {
  const firstPose = rig.samplePose("A person waving", 0.15, 5);
  const secondPose = rig.samplePose("A person waving", 0.42, 5);
  assert.notEqual(firstPose.rightForearmAngle, secondPose.rightForearmAngle);
  const first = rig.buildSkeleton({ ox: 400, oy: 300, unit: 1, pose: firstPose });
  const second = rig.buildSkeleton({ ox: 400, oy: 300, unit: 1, pose: secondPose });
  assert.ok(distance(first.rightWrist, second.rightWrist) > 4);
});

test("walking alternates legs and keeps fixed parent-child limb lengths", () => {
  const firstPose = rig.samplePose("A person walking", 0.2, 6);
  const secondPose = rig.samplePose("A person walking", 0.8, 6);
  const first = rig.buildSkeleton({ ox: 400, oy: 300, unit: 1.3, pose: firstPose });
  const second = rig.buildSkeleton({ ox: 400, oy: 300, unit: 1.3, pose: secondPose });
  assert.ok(distance(first.leftAnkle, second.leftAnkle) > 8);
  assert.ok(Math.abs(distance(first.leftHip, first.leftKnee) - 58 * 1.3) < 1e-8);
  assert.ok(Math.abs(distance(first.leftKnee, first.leftAnkle) - 61 * 1.3) < 1e-8);
  assert.ok(Math.abs(distance(first.rightShoulder, first.rightElbow) - 48 * 1.3) < 1e-8);
  assert.ok(Math.abs(distance(first.rightElbow, first.rightWrist) - 45 * 1.3) < 1e-8);
});

test("jump motion rises and returns along a smooth authored arc", () => {
  const low = rig.samplePose("A person jumping", 0.05, 4);
  const high = rig.samplePose("A person jumping", 0.84, 4);
  const falling = rig.samplePose("A person jumping", 1.25, 4);
  assert.ok(high.lift > low.lift);
  assert.ok(Number.isFinite(falling.lift) && falling.lift >= 0);
});

test("keyframe curve clamps its endpoints and interpolates smoothly", () => {
  const keys = [[0, 0], [0.5, 1], [1, 0]];
  assert.equal(rig.sampleCurve(keys, -1), 0);
  assert.equal(rig.sampleCurve(keys, 2), 0);
  assert.equal(rig.sampleCurve(keys, 0.5), 1);
  const left = rig.sampleCurve(keys, 0.49);
  const right = rig.sampleCurve(keys, 0.51);
  assert.ok(Math.abs(right - left) < 0.02);
});

test("invalid times stay finite and progress is bounded", () => {
  for (const time of [-10, 0, 2, 100, NaN, Infinity]) {
    const pose = rig.samplePose("A character dances", time, 4);
    assert.ok(Number.isFinite(pose.lift));
    assert.ok(pose.progress >= 0 && pose.progress <= 1);
  }
});
