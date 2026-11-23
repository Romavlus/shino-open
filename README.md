# Shino Open 1.4.0

**English** · [Русский](README.ru.md)

Shino is an animated 3D desktop companion for macOS. Pick from six outfits, place up to ten characters on your desktop, or move them together onto a full-screen background on a second monitor. Each character can walk, idle and act out short scenes.

[Download for Apple Silicon](https://raw.githubusercontent.com/Romavlus/shino-open/v1.4.0/Downloads/Shino-Open-1.4.0-macOS-arm64.zip) · [Previous version (1.3.0)](https://raw.githubusercontent.com/Romavlus/shino-open/v1.4.0/Downloads/Shino-Open-1.3.0-macOS-arm64.zip)

## Getting started

The download requires macOS 13 or later. Unzip it and move **Shino Open.app** to your Applications folder. The build is ad hoc signed. **The app interface in version 1.4.0 is in Russian.** The controls below include the labels you will see on screen.

1. Open the app and click the bow icon in the macOS menu bar. Choose **Примерочная движений…** (Motion Studio) to preview Shino. Drag to rotate, scroll to zoom, or click **Портрет** for a close-up. Click **Пауза** to hold a pose while you orbit the character.
2. On the desktop, drag Shino to move her. Hold **⌘ Command** and drag to rotate her. She turns to face the direction of travel before walking, then returns to your chosen angle when she stops.
3. Open **Поведение** (Behavior) to set character size, facial expression intensity, scene frequency and scheduled visits. You can set how often Shino appears and how long she stays. Settings save automatically.

## Outfits and motion

Choose an outfit under **Персонаж** (Character) in the bow menu or at the top of the studio. The six looks are Original Shino, Cherry Uniform, Dress with Cardigan, 25C Black Biker Jacket, 29 Sea Breeze and 33C Coral Silk. Switching outfits updates the desktop and studio together. The studio keeps the camera angle, zoom, animation position and pause state so you can compare outfits in the same pose.

Use the **−** and **+** controls at the top of the studio or enter a number from 1 to 10. Pick an outfit for each slot, or choose **Нет** (None) to leave it empty. Reducing the slot count remembers the hidden selections for later. Under **Поведение**, choose shared settings or adjust each character individually.

The motion library includes three walks, three walking transitions, four idle animations and twenty short scenes. A selected scene loops in the studio. Choose **Показать все сценки** (Play all scenes) from the bow menu to play the full sequence once. All active characters perform each scene in sync, in place, at the first character’s pace. Select the command again to stop.

## Full-screen mode

Open **Сцена во весь экран** (Full-screen scene) in the bow menu and select a monitor. The **Открыть сцену во весь экран** button in Behavior reopens the last display you chose. The first time, it uses the display with the most characters.

Choose **Фон полноэкранной сцены** (Scene background) in Behavior, or right-click an empty area of the scene. There are five gradients and three illustrated landscapes. Stars twinkle over the lake unless Reduce Motion is enabled in macOS. Walking, scenes, rotation and visit schedules continue on the selected monitor. Press **Esc** in the scene or choose **Вернуться на рабочий стол** to return the characters to their desktop positions.

## Build and verify

On a Mac with Python 3 and the Xcode Command Line Tools, run these commands from the repository root. The build includes the models, motions and rendering libraries, targets the architecture of the build machine, and signs the app locally. Its bundle identifier is `org.shinoopen.desktop`.

```sh
python3 build.py --output "$HOME/Applications/Shino Open.app"
open "$HOME/Applications/Shino Open.app" --args --studio
```

The first check covers windows, controls, scheduling, poses and frame timing using temporary settings. The second exercises outfit switching on the desktop and in the studio, playback and scheduled appearances.

```sh
"$HOME/Applications/Shino Open.app/Contents/MacOS/Shino" --verify
"$HOME/Applications/Shino Open.app/Contents/MacOS/Shino" --verify-models
```

## Artwork, motion and lighting

The outfits share Shino’s base model, motion library and facial expressions. The dress retains the original body underneath. Its waistband stays anchored while the folds respond to gravity, movement and contact with the legs. Garment geometry and materials are in `Assets/Wardrobe`. To regenerate them, install NumPy and Pillow in your Python environment and run:

```sh
python3 MotionSource/tailor_shino.py
python3 MotionSource/atelier.py
```

The second script builds the patterns, materials and spring-bone chains for outfits 25C, 29 and 33C.

The animation sources are `MotionSource/gestures.py`, `MotionSource/animate.py` and the KayKit motion tracks in `kaykit.json`. The first Blender command below writes VRMA clips into `Motions`. The second also regenerates `MotionSource/Сино — анимации.blend`, so save any manual edits to that scene separately first.

```sh
blender -b --python-exit-code 1 -P MotionSource/animate.py
blender -b --python-exit-code 1 -P MotionSource/animate.py -- --blend
```

Select the armature in Blender’s Action Editor to inspect the 31 actions, including breathing. At runtime, hair and clothing physics run on top of the skeletal animation. The desktop and studio share the lighting, shadows and MToon highlights in `Source/lighting.js`. Lighting responds to the pose and camera angle, including when you rotate a paused character.

## Licenses

Shino’s model, KayKit motion assets, additional gestures and illustrated artwork are distributed under [CC0](Licenses/CC0-1.0.txt). The project’s own code uses [0BSD](LICENSE). The app includes the MIT notices for Three.js, three-vrm and three-vrm-animation. Keep those notices when redistributing the rendering libraries. See [asset provenance](Licenses/ASSETS.txt) and the [license files](Licenses).
