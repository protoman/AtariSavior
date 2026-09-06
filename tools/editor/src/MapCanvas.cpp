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

#include "MapCanvas.hpp"
#include <QPainter>
#include <QMouseEvent>
#include <cmath>

namespace editor {

// The Savannah Atari prototype renders rooms as a mirrored playfield (the TIA
// reflects the playfield). The editor shows the full mirrored stage and maps
// canvas column q to the room's data column: q for q<width, else 2*width-1-q.
// Editing either half edits the mirrored original tile, keeping rooms symmetric
// by construction (required by the reflected playfield).
// All geometry is derived from the loaded room's width/height so the editor
// stays correct for any room size the game data may contain.

static int DisplayColumnsFor(int roomWidth) { return roomWidth * 2; }

static int MirrorColumn(int displayCol, int roomWidth) {
    int displayCols = DisplayColumnsFor(roomWidth);
    return (displayCol < roomWidth) ? displayCol : (displayCols - 1 - displayCol);
}

MapCanvas::MapCanvas(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    // Default 20x16 stage until a room is loaded.
    setFixedSize(DisplayColumnsFor(kDefaultRoomWidth) * m_tileSize,
                 kDefaultRoomHeight * m_tileSize);
}

void MapCanvas::SetLevelData(hero::LevelData* levelData, int activeRoomIndex) {
    m_levelData = levelData;
    m_activeRoomIndex = activeRoomIndex;
    UpdateSizeForRoom();
    update();
}

void MapCanvas::SetActiveRoom(int roomIndex) {
    m_activeRoomIndex = roomIndex;
    UpdateSizeForRoom();
    update();
}

void MapCanvas::SetTileSize(int size) {
    if (size <= 0) size = 24;
    m_tileSize = size;
    UpdateSizeForRoom();
    update();
}

void MapCanvas::UpdateSizeForRoom() {
    int w = kDefaultRoomWidth;
    int h = kDefaultRoomHeight;
    if (m_levelData && m_activeRoomIndex >= 0 &&
        m_activeRoomIndex < (int)m_levelData->rooms.size()) {
        const auto& room = m_levelData->rooms[m_activeRoomIndex];
        w = room.width > 0 ? room.width : kDefaultRoomWidth;
        h = room.height > 0 ? room.height : kDefaultRoomHeight;
    }
    setFixedSize(DisplayColumnsFor(w) * m_tileSize, h * m_tileSize);
}

namespace {
int RoomWidthOf(const hero::RoomData& room) {
    return room.width > 0 ? room.width : MapCanvas::kDefaultRoomWidth;
}
int RoomHeightOf(const hero::RoomData& room) {
    return room.height > 0 ? room.height : MapCanvas::kDefaultRoomHeight;
}
} // namespace

QColor MapCanvas::GetTileColor(int tileType) const {
    if (!m_levelData) return QColor(30, 30, 30);

    switch (static_cast<hero::TileType>(tileType)) {
        case hero::TileType::AIR:
            return QColor(15, 15, 20);
        case hero::TileType::SOLID_WALL:
            return QColor(m_levelData->wall_r, m_levelData->wall_g, m_levelData->wall_b);
        case hero::TileType::FRAGILE_WALL:
            return QColor(210, 140, 50);
        case hero::TileType::REINFORCED_WALL:
            return QColor(160, 40, 40);
        case hero::TileType::LAVA:
            return QColor(220, 60, 0);
        case hero::TileType::WATER:
            return QColor(0, 90, 180);
        case hero::TileType::RAFT:
            return QColor(140, 80, 20);
        case hero::TileType::MAGMA_FALL:
            return QColor(255, 100, 0);
        default:
            return QColor(15, 15, 20);
    }
}

void MapCanvas::paintEvent(QPaintEvent* /*event*/) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // Canvas background
    painter.fillRect(rect(), QColor(10, 10, 15));

    if (!m_levelData || m_activeRoomIndex < 0 || m_activeRoomIndex >= (int)m_levelData->rooms.size()) {
        painter.setPen(Qt::white);
        painter.drawText(rect(), Qt::AlignCenter, "No Room Loaded");
        return;
    }

    const auto& room = m_levelData->rooms[m_activeRoomIndex];
    const int roomWidth = RoomWidthOf(room);
    const int roomHeight = RoomHeightOf(room);
    const int displayCols = DisplayColumnsFor(roomWidth);

    // Render Grid & Tiles (full mirrored stage)
    for (int y = 0; y < roomHeight; ++y) {
        for (int dcol = 0; dcol < displayCols; ++dcol) {
            int x = MirrorColumn(dcol, roomWidth);
            int tileType = room.tiles[y * roomWidth + x];
            QRect tileRect(dcol * m_tileSize, y * m_tileSize, m_tileSize, m_tileSize);

            QColor color = GetTileColor(tileType);
            painter.fillRect(tileRect, color);

            // Draw tile border
            painter.setPen(QColor(40, 40, 50));
            painter.drawRect(tileRect);

            // Tile specific overlays
            if (tileType == (int)hero::TileType::FRAGILE_WALL) {
                painter.setPen(QColor(140, 90, 30));
                painter.drawLine(tileRect.topLeft(), tileRect.bottomRight());
            } else if (tileType == (int)hero::TileType::REINFORCED_WALL) {
                painter.setPen(QColor(220, 80, 80));
                painter.drawRect(tileRect.adjusted(3, 3, -3, -3));
            }
        }
    }

    // Draw a seam marker at the mirror axis (between room columns width-1 and width)
    int seamX = roomWidth * m_tileSize;
    painter.setPen(QPen(QColor(90, 90, 110), 2));
    painter.drawLine(seamX, 0, seamX, roomHeight * m_tileSize);

    // Render Player Start position if in this room
    if (m_levelData->start_room == m_activeRoomIndex) {
        int px = (int)(m_levelData->start_x * m_tileSize);
        int py = (int)(m_levelData->start_y * m_tileSize);
        QRect playerRect(px - 12, py - 12, 24, 24);

        painter.setBrush(QColor(255, 220, 0));
        painter.setPen(Qt::black);
        painter.drawEllipse(playerRect);
        painter.drawText(playerRect, Qt::AlignCenter, "P");
    }

    // Render Miner Goal position if in this room
    if (m_levelData->miner_room == m_activeRoomIndex) {
        int mx = (int)(m_levelData->miner_x * m_tileSize);
        int my = (int)(m_levelData->miner_y * m_tileSize);
        QRect minerRect(mx - 12, my - 12, 24, 24);

        painter.setBrush(QColor(255, 140, 180));
        painter.setPen(Qt::black);
        painter.drawEllipse(minerRect);
        painter.drawText(minerRect, Qt::AlignCenter, "M");
    }

    // Render Lamps in room
    for (const auto& lamp : room.lamps) {
        int lx = (int)(lamp.x * m_tileSize);
        int ly = (int)(lamp.y * m_tileSize);
        int bulbSize = 12;

        // Glowing bulb
        painter.setBrush(lamp.lit ? QColor(255, 230, 80) : QColor(110, 110, 110));
        painter.setPen(Qt::black);
        painter.drawEllipse(lx - bulbSize / 2, ly - bulbSize, bulbSize, bulbSize);

        // Pole and base
        painter.setPen(QColor(150, 150, 150));
        painter.drawLine(lx, ly, lx, ly + 10);
        painter.setBrush(QColor(120, 120, 120));
        painter.drawRect(lx - 5, ly + 10, 10, 3);

        painter.setPen(Qt::black);
        painter.drawText(QRect(lx - 10, ly - bulbSize - 14, 20, 14), Qt::AlignCenter, "L");
    }

    // Render Enemies in room
    for (const auto& enemy : room.enemies) {
        int ex = (int)(enemy.x * m_tileSize);
        int ey = (int)(enemy.y * m_tileSize);
        QRect enemyRect(ex, ey, m_tileSize - 4, m_tileSize - 4);

        QColor eColor;
        QString label;
        switch (static_cast<hero::EnemyType>(enemy.type)) {
            case hero::EnemyType::SPIDER: eColor = QColor(240, 200, 0); label = "S"; break;
            case hero::EnemyType::BAT: eColor = QColor(220, 40, 60); label = "B"; break;
            case hero::EnemyType::SNAKE: eColor = QColor(40, 200, 40); label = "K"; break;
            case hero::EnemyType::TENTACLE: eColor = QColor(200, 60, 200); label = "T"; break;
            case hero::EnemyType::GIANT_MOTH: eColor = QColor(190, 160, 120); label = "M"; break;
        }

        painter.setBrush(eColor);
        painter.setPen(Qt::black);
        painter.drawRoundedRect(enemyRect, 6, 6);
        painter.drawText(enemyRect, Qt::AlignCenter, label);
    }
}

void MapCanvas::ApplyBrushAt(int tileX, int tileY) {
    if (!m_levelData || m_activeRoomIndex < 0 || m_activeRoomIndex >= (int)m_levelData->rooms.size()) return;
    auto& room = m_levelData->rooms[m_activeRoomIndex];

    if (tileX < 0 || tileX >= room.width || tileY < 0 || tileY >= room.height) return;

    int brushVal = static_cast<int>(m_currentBrush);

    if (brushVal >= 0 && brushVal <= 7) {
        // Tile brush
        room.tiles[tileY * room.width + tileX] = brushVal;
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::SET_PLAYER_START) {
        m_levelData->start_room = m_activeRoomIndex;
        m_levelData->start_x = (float)tileX + 0.5f;
        m_levelData->start_y = (float)tileY;
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::SET_MINER_GOAL) {
        m_levelData->miner_room = m_activeRoomIndex;
        m_levelData->miner_x = (float)tileX + 0.5f;
        m_levelData->miner_y = (float)tileY;
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::ADD_SPIDER || m_currentBrush == BrushTool::ADD_BAT ||
               m_currentBrush == BrushTool::ADD_SNAKE || m_currentBrush == BrushTool::ADD_TENTACLE ||
               m_currentBrush == BrushTool::ADD_MOTH) {
        hero::EnemyData eData;
        if (m_currentBrush == BrushTool::ADD_SPIDER) eData.type = (int)hero::EnemyType::SPIDER;
        else if (m_currentBrush == BrushTool::ADD_BAT) eData.type = (int)hero::EnemyType::BAT;
        else if (m_currentBrush == BrushTool::ADD_SNAKE) eData.type = (int)hero::EnemyType::SNAKE;
        else if (m_currentBrush == BrushTool::ADD_TENTACLE) eData.type = (int)hero::EnemyType::TENTACLE;
        else if (m_currentBrush == BrushTool::ADD_MOTH) eData.type = (int)hero::EnemyType::GIANT_MOTH;

        eData.x = (float)tileX;
        eData.y = (float)tileY;
        eData.range_min = (float)std::max(0, tileX - 3);
        eData.range_max = (float)std::min(15, tileX + 3);
        eData.speed = 1.5f;
        eData.dir = 1;

        room.enemies.push_back(eData);
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::ADD_LAMP) {
        // Replace any lamp already on this tile, otherwise add a new one
        for (auto& lamp : room.lamps) {
            if ((int)std::floor(lamp.x) == tileX && (int)std::floor(lamp.y) == tileY) {
                lamp.x = (float)tileX + 0.5f;
                lamp.y = (float)tileY + 0.5f;
                lamp.lit = true;
                emit levelModified();
                update();
                return;
            }
        }

        hero::LampData lamp;
        lamp.x = (float)tileX + 0.5f;
        lamp.y = (float)tileY + 0.5f;
        lamp.lit = true;
        room.lamps.push_back(lamp);
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::DELETE_ENTITY) {
        // Remove enemy or lamp near tileX, tileY
        for (auto it = room.enemies.begin(); it != room.enemies.end(); ++it) {
            if ((int)std::floor(it->x) == tileX && (int)std::floor(it->y) == tileY) {
                room.enemies.erase(it);
                emit levelModified();
                update();
                return;
            }
        }
        for (auto it = room.lamps.begin(); it != room.lamps.end(); ++it) {
            if ((int)std::floor(it->x) == tileX && (int)std::floor(it->y) == tileY) {
                room.lamps.erase(it);
                emit levelModified();
                update();
                return;
            }
        }
    }
}

void MapCanvas::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::LeftButton) {
        MouseToTile(event->position(), /*apply=*/true);
    }
}

void MapCanvas::mouseMoveEvent(QMouseEvent* event) {
    MouseToTile(event->position(), event->buttons() & Qt::LeftButton);
}

void MapCanvas::MouseToTile(const QPointF& pos, bool apply) {
    int roomWidth = kDefaultRoomWidth;
    if (m_levelData && m_activeRoomIndex >= 0 &&
        m_activeRoomIndex < (int)m_levelData->rooms.size())
        roomWidth = RoomWidthOf(m_levelData->rooms[m_activeRoomIndex]);

    int displayCol = (int)(pos.x() / m_tileSize);
    int tileX = MirrorColumn(displayCol, roomWidth);
    int tileY = (int)(pos.y() / m_tileSize);
    emit mouseMovedToTile(tileX, tileY);
    if (apply)
        ApplyBrushAt(tileX, tileY);
}

} // namespace editor
