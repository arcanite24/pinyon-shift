#!/usr/bin/env python3
"""Write the built-in immersive camera mod's CameraPhysics.xml merge (#419).

FH1 drives its cameras from layered effects in media/camera.zip's
CameraPhysics.xml: each layer maps an input (g-forces, speed, a constant)
through a curve, optional noise and a spring to a camera offset. This tool
writes Pinyon Shift's own extra layers (G-forces, the throttle and brake
jolt, corner lean, speed shake, braking vibration, breathing and head sway)
as a merge that appends them (`pinyon-add`) and raises each camera's
NumLayers. The stock counts below are the disc's; nothing else from the disc
is used. Edit the tuning here and run it again.

  build-immersive-camera.py [output]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = (ROOT / "mods_src" / "builtin" / "immersive_camera" / "merge" / "media"
           / "camera.zip" / "CameraPhysics.xml")

STOCK = {"FollowCam": 74, "FollowCam2": 69, "DriverCam": 51, "Hood": 47, "BumperHigh": 46}


def f(v):
    return f"{v:.6f}"


def curve(prefix, points):
    attrs = {f"{prefix}Mapping": {1: "ConstantOne", 2: "Linear", 3: "ThreePoint", 5: "FivePoint"}[len(points)] if points else "ConstantOne"}
    if len(points) >= 3:
        for i, (x, y) in enumerate(points):
            attrs[f"{prefix}CurveInput{i}"] = f(x)
            attrs[f"{prefix}CurveOutput{i}"] = f(y)
        attrs[f"{prefix}CurveMirrored"] = "0"
    return attrs


def layer(input_type, output, param, points=None, clamp=None, noise=None, spring=None,
          derivative=False):
    a = {"Enabled": "1", "InputType": input_type,
         "NoiseType": noise[0] if noise else "None", "OutputType": output,
         "InputTakeDerivative": "1" if derivative else "0"}
    if clamp:
        a["InputClampMin"], a["InputClampMax"] = f(clamp[0]), f(clamp[1])
    a["InputMagAttackDecay"] = "0"
    if noise:
        _, freq, seed = noise
        a["InputToNoiseFreqMapping"] = "Linear"
        a["NoiseFreq"], a["NoiseSeed"] = f(freq), f(seed)
        a["NoiseOutputRangeMin"], a["NoiseOutputRangeMax"] = f(-1), f(1)
    if points is None:
        a["InputToParamMapping"] = "ConstantOne" if input_type == "ConstantOne" else "Linear"
    else:
        a.update(curve("InputToParam", points))
    for axis, v in zip("xyzw", list(param) + [0] * (4 - len(param))):
        a[f"Param.{axis}"] = f(v)
    if spring:
        a["Sprung"], a["SpringK"], a["SpringDPercent"] = "1", f(spring[0]), f(spring[1])
    else:
        a["Sprung"] = "0"
    return a


def camera_layers(s, cockpit):
    """s scales every effect; cockpit adds lean, shake and head motion."""
    out = []
    # G-forces: pushed back under acceleration, thrown forward and down
    # under braking, sprung so it settles with a little overshoot.
    out.append(layer("Gs_Longitudinal", "CarSpaceXYZOffset", (0, 0, -0.035 * s),
                     [(0, 0), (0.3, 0.5), (1.0, 1.0)], (0, 1.0), spring=(140, 0.55)))
    out.append(layer("Gs_Longitudinal", "CarSpaceXYZOffset", (0, 0.008 * s, -0.045 * s),
                     [(-1.5, -1.2), (-1.0, -1.0), (0, 0)], (-1.5, 0), spring=(120, 0.5)))
    out.append(layer("Gs_Longitudinal", "CarSpaceYPROffset", (0, -0.9 * s, 0),
                     [(-1.5, -1.2), (-1.0, -1.0), (0, 0)], (-1.5, 0), spring=(120, 0.5)))
    # The jolt when throttle or brake goes on: the change in g, quickly
    # damped.
    out.append(layer("Gs_Longitudinal", "CarSpaceYPROffset", (0, 0.6 * s, 0),
                     [(-6, -1), (0, 0), (6, 1)], (-6, 6), spring=(300, 0.35), derivative=True))
    if not cockpit:
        return out
    # Corner lean: the head rolls and slides into the turn.
    for side in (-1, 1):
        clamp = (-1.2, 0) if side < 0 else (0, 1.2)
        pts = [(-1.2, -1), (-0.6, -0.5), (-0.1, 0)] if side < 0 else [(0.1, 0), (0.6, 0.5), (1.2, 1)]
        out.append(layer("Gs_Lateral", "CarSpaceYPROffset", (0, 0, -0.9 * s), pts, clamp,
                         spring=(200, 0.6)))
        out.append(layer("Gs_Lateral", "CarSpaceXYZOffset", (0.02 * s, 0, 0), pts, clamp,
                         spring=(200, 0.6)))
    # High-speed shake, from 40 mph up (stock starts at 140).
    out.append(layer("SpeedMPH", "CameraSpaceYPROffset", (0.10 * s, 0.14 * s, 0.08 * s),
                     [(40, 0), (80, 0.3), (120, 0.6), (160, 0.85), (200, 1)], (0, 240),
                     noise=("Simplex", 18, 3.1)))
    # Hard braking at the limit: a fine vibration.
    out.append(layer("Gs_Longitudinal", "CameraSpaceYPROffset", (0.05 * s, 0.12 * s, 0),
                     [(-1.3, 1), (-1.0, 0.6), (-0.7, 0)], (-1.5, 0), noise=("Simplex", 38, 7.7)))
    # Breathing and head sway: slow layers at unrelated rates.
    out.append(layer("ConstantOne", "CarSpaceXYZOffset", (0, 0.0025 * s, 0),
                     noise=("Sin", 1.6, 0.0)))
    out.append(layer("ConstantOne", "CarSpaceXYZOffset", (0, 0.0012 * s, 0),
                     noise=("Sin", 2.9, 1.3)))
    out.append(layer("ConstantOne", "CameraSpaceYPROffset", (0.12 * s, 0, 0.08 * s),
                     noise=("Simplex", 0.7, 5.3)))
    return out


def main(path):
    cams = {"DriverCam": camera_layers(1.0, True), "Hood": camera_layers(0.8, True),
            "BumperHigh": camera_layers(0.6, False), "FollowCam": camera_layers(0.5, False),
            "FollowCam2": camera_layers(0.5, False)}
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             "<!-- Immersive camera for Pinyon Shift: layers appended to FH1's camera",
             "     physics (G-forces, the throttle and brake jolt, corner lean, speed",
             "     shake, braking vibration, breathing and head sway). Pinyon Shift's own",
             "     tuning, inspired by Immersive Camera Enhanced for FH6; nothing is taken",
             "     from that mod. Generated by tools/build-immersive-camera.py. -->",
             "<CameraPhysics>"]
    for cam, layers in cams.items():
        lines.append(f'  <{cam} NumLayers="{STOCK[cam] + len(layers)}">')
        for a in layers:
            lines.append("    <Layer pinyon-add=\"true\" " +
                         " ".join(f'{k}="{v}"' for k, v in a.items()) + "/>")
        lines.append(f"  </{cam}>")
    lines.append("</CameraPhysics>")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
