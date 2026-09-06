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
#include "LevelData.hpp"

namespace editor {

enum class BrushTool {
    ERASE_AIR = 0,
    SOLID_WALL = 1,
    FRAGILE_WALL = 2,
    REINFORCED_WALL = 3,
    LAVA = 4,
    WATER = 5,
    RAFT = 6,
    MAGMA_FALL = 7,
    SET_PLAYER_START = 8,
    SET_MINER_GOAL = 9,
    ADD_SPIDER = 10,
    ADD_BAT = 11,
    ADD_SNAKE = 12,
    ADD_TENTACLE = 13,
    DELETE_ENTITY = 14,
    ADD_LAMP = 15,
    ADD_MOTH = 16
};

class MapCanvas : public QWidget {
    Q_OBJECT

public:
    explicit MapCanvas(QWidget* parent = nullptr);

    // Fallback size used until a room is loaded.
    static constexpr int kDefaultRoomWidth = 20;
    static constexpr int kDefaultRoomHeight = 16;

    void SetLevelData(hero::LevelData* levelData, int activeRoomIndex);
    void SetActiveRoom(int roomIndex);
    void SetTileSize(int size);
    int TileSize() const { return m_tileSize; }
    void SetCurrentBrush(BrushTool brush) { m_currentBrush = brush; }

    BrushTool GetCurrentBrush() const { return m_currentBrush; }

signals:
    void levelModified();
    void mouseMovedToTile(int tileX, int tileY);

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;

private:
    void ApplyBrushAt(int tileX, int tileY);
    void MouseToTile(const QPointF& pos, bool apply);
    QColor GetTileColor(int tileType) const;
    void UpdateSizeForRoom();

    hero::LevelData* m_levelData = nullptr;
    int m_activeRoomIndex = 0;
    BrushTool m_currentBrush = BrushTool::SOLID_WALL;
    int m_tileSize = 24;
};

} // namespace editor
