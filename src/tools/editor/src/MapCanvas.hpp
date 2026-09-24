/*
 * Savior SDL - H.E.R.O. Level Editor
 * Copyright (C) 2026 Savior SDL Team
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

#pragma once

#include <QWidget>
#include <QPointF>
#include <QKeyEvent>
#include "LevelData.hpp"

namespace editor {

enum class BrushTool {
    // Model tab: tile brushes (values match TileType for tile editing)
    ERASE_AIR = 0,
    SOLID_WALL = 1,
    HOT_ROCK_WALL = 8,
    // Level tab: entity brushes
    SET_MINER_GOAL = 9,
    ADD_SPIDER = 10,
    ADD_BAT = 11,
    ADD_SNAKE = 12,
    ADD_TENTACLE = 13,
    ADD_MOTH = 14,
    ADD_LAMP = 15,
    ADD_RAFT = 16,
    ADD_MAGMA = 17,
    DELETE_ENTITY = 18
};

class MapCanvas : public QWidget {
    Q_OBJECT

public:
    explicit MapCanvas(QWidget* parent = nullptr);

    // Fallback size used until a room is loaded.
    static constexpr int kDefaultRoomWidth = 20;
    static constexpr int kDefaultRoomHeight = 12;  // playable rows

    void SetLevelData(hero::LevelData* levelData, std::vector<hero::ModelData>* models, int activeRoomIndex);
    void SetActiveRoom(int roomIndex);
    void SetTileSize(int size);
    int TileSize() const { return m_tileSize; }
    void SetCurrentBrush(BrushTool brush) { m_currentBrush = brush; }
    void SetEditMode(bool modelMode) { m_modelMode = modelMode; }
    void SetActiveModel(int modelIndex);
    void SetModels(std::vector<hero::ModelData>* models) { m_models = models; }

    BrushTool GetCurrentBrush() const { return m_currentBrush; }

    // Initial facing for newly placed enemies: +1 = right, -1 = left.
    void SetInitialFacing(int dir) { m_initialFacing = (dir < 0) ? -1 : 1; }
    int InitialFacing() const { return m_initialFacing; }

signals:
    void levelModified();
    void mouseMovedToTile(int tileX, int tileY);
    void facingChanged(int dir);

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private:
    void ApplyBrushAt(int tileX, int entityX, int tileY);
    void MouseToTile(const QPointF& pos, bool apply);
    QColor GetTileColor(int tileType, int tileY) const;
    void UpdateSizeForRoom();
    void DrawFacingArrow(QPainter& painter, const QRect& enemyRect, int dir) const;
    // Miner + enemies + lamps in the active room (flicker budget).
    int CountRoomElements() const;
    // False + warning dialog if adding would exceed kMaxRoomElements.
    bool AllowAddElement();
    // True if any miner/enemy/lamp already occupies this tile row (room space).
    bool ElementInRow(int tileY) const;
    // False + warning if row already has an element (except optional ignoreY
    // for the miner's current row when re-placing the miner in the same room).
    bool AllowElementInRow(int tileY, int ignoreY = -1);

    hero::LevelData* m_levelData = nullptr;
    std::vector<hero::ModelData>* m_models = nullptr;
    int m_activeRoomIndex = 0;
    int m_activeModelIndex = 0;
    bool m_modelMode = true;
    BrushTool m_currentBrush = BrushTool::SOLID_WALL;
    int m_tileSize = 24;
    int m_initialFacing = 1;

    // GRP1 flicker budget: miner + enemies + lamps share one sprite slot.
    static constexpr int kMaxRoomElements = 3;
};

} // namespace editor
