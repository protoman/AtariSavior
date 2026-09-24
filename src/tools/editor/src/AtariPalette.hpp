/*
 * Savior SDL - H.E.R.O. Level Editor
 * Atari 2600 TIA NTSC color palette (128 colors) and picker dialog.
 *
 * The 2600's TIA color byte is structured as `(luminance << 4) | hue`:
 *   16 hues  (low nibble, 0-15)
 *   8 luminance steps used by the classic 128-color NTSC chart (high nibble 0-7)
 *
 * The RGB values mirror the well-known Stella NTSC 128-color chart (also used
 * by batari Basic tooling). They are approximations of what a TV shows; the
 * authoritative value is the byte itself, which is what the ROM writes to
 * COLU* and what the game stores/consumes.
 */

#pragma once

#include <QColor>
#include <QString>
#include <vector>

class QWidget; // forward declare for the picker signature

namespace editor {
// Returns the RGB colour of the classic chart cell (hue 0-15, luma 0-7).
QColor NtscRgb(int hue, int luma);

// Returns the RGB colour for a TIA colour byte.
QColor NtscRgbForByte(int colorByte);

// Current hue (0-15) of a TIA colour byte.
int NtscHue(int colorByte);

// Current luma (0-15) of a TIA colour byte.
int NtscLuma(int colorByte);

// Short descriptive name for a hue (e.g. "orange", "sky blue").
QString NtscHueName(int hue);

// Finds the palette byte whose RGB is nearest to `color` (squared-distance match).
int NearestNtscByte(const QColor& color);

// Modal NTSC palette grid picker. Returns the chosen TIA colour byte, or -1 if
// the user cancels. `current` (optional) preselects the nearest palette cell.
int PickNtscColor(QWidget* parent, const QColor& current);

} // namespace editor