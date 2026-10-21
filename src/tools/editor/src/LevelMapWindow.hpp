/*
 * Savior AI - Atari 2600
 * Copyright (C) 2026 Savior SDL Team
 *
 * View -> Map: a whole-level overview. Every room is drawn at its C1 grid
 * position with its three band rows, and a corridor is drawn between two
 * rooms only when BOTH sides carve the shared opening (the same adjacency
 * rule the kernel uses at run time — a one-sided carve tears the transition).
 *
 * The window is read-only: it never writes level data. MainWindow refreshes
 * it on every edit (levelModified / undo / level switch / generate).
 */

#pragma once

#include <QDialog>
#include <QPixmap>
#include <QString>
#include <vector>

#include "LevelData.hpp"

class QScrollArea;

namespace editor {

class LevelMapView;   // paints the rooms on the 15 x 15 C1 grid

class LevelMapWindow : public QDialog {
    Q_OBJECT

public:
    explicit LevelMapWindow(QWidget* parent = nullptr);

    // Copy the level + the model library used to resolve each room's shape.
    // `levelNumber` is 1-based (the user counts from 1).
    void SetLevel(const hero::LevelData& level,
                  const std::vector<hero::ModelData>& models,
                  int levelNumber);

    // Full canvas at its natural size (used by the --map-png hook).
    QPixmap RenderPixmap();

private:
    LevelMapView* m_view = nullptr;
    QScrollArea* m_scroll = nullptr;
};

// Dev/CI hook: render one level's map to a PNG without opening a window
// (needs a QApplication). Returns false when the level index is out of range
// or the file cannot be written.
bool RenderLevelMapPng(const hero::LevelData& level,
                       const std::vector<hero::ModelData>& models,
                       int levelNumber, const QString& path);

}  // namespace editor
