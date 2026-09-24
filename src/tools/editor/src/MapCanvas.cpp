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
#include <QKeyEvent>
#include <QMessageBox>
#include <QPolygonF>
#include <cmath>

namespace editor {

// The Savannah Atari prototype renders rooms as a mirrored playfield (the TIA
// reflects the playfield). The editor shows the full mirrored stage and maps
// canvas column q to the room's data column: q for q<width, else 2*width-1-q.
// Editing either half edits the mirrored original tile, keeping rooms symmetric
// by construction (required by the reflected playfield).
// Entities (enemies, lamps) are deliberately EXEMPT from the mirror rule: they
// are positioned/stored/rendered in full-stage columns 0..2*width-1 so each
// screen half can have its own objects.
// All geometry is derived from the loaded room's width/height so the editor
// stays correct for any room size the game data may contain.

static int DisplayColumnsFor(int roomWidth) { return roomWidth * 2; }

static int MirrorColumn(int displayCol, int roomWidth) {
    int displayCols = DisplayColumnsFor(roomWidth);
    return (displayCol < roomWidth) ? displayCol : (displayCols - 1 - displayCol);
}

// Tile height so the whole visible map (DisplayColumnsFor(roomWidth) columns x
// roomHeight rows) renders at a 4:3 aspect, matching its proportions on the
// game screen. Cells are therefore rectangles, not squares.
static int CellHeightFor(int cellWidth, int displayCols, int roomHeight) {
    if (roomHeight <= 0 || displayCols <= 0) return cellWidth;
    return std::max(1, (int)std::lround(cellWidth * (double)displayCols * 3.0 /
                                        (double)(roomHeight * 4)));
}

MapCanvas::MapCanvas(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);  // F toggles initial facing
    // Default 20x12 stage until a room is loaded. The map area only: the grey
    // HUD band is drawn by the game kernel and is not shown/edited here.
    setFixedSize(DisplayColumnsFor(kDefaultRoomWidth) * m_tileSize,
                 kDefaultRoomHeight * CellHeightFor(m_tileSize,
                     DisplayColumnsFor(kDefaultRoomWidth), kDefaultRoomHeight));
}

void MapCanvas::SetLevelData(hero::LevelData* levelData, std::vector<hero::ModelData>* models, int activeRoomIndex) {
    m_levelData = levelData;
    m_models = models;
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

namespace {
hero::ModelData* GetModelForRoom(hero::LevelData* level, std::vector<hero::ModelData>* models, int roomIdx) {
    if (!level || !models || roomIdx < 0 || roomIdx >= (int)level->rooms.size()) return nullptr;
    int mid = level->rooms[roomIdx].model_id;
    if (mid < 0 || mid >= (int)models->size()) return nullptr;
    return &(*models)[mid];
}
int RoomWidthOf(hero::LevelData* level, std::vector<hero::ModelData>* models, int roomIdx) {
    auto* m = GetModelForRoom(level, models, roomIdx);
    return (m && m->width > 0) ? m->width : MapCanvas::kDefaultRoomWidth;
}
int RoomHeightOf(hero::LevelData* level, std::vector<hero::ModelData>* models, int roomIdx) {
    auto* m = GetModelForRoom(level, models, roomIdx);
    return (m && m->height > 0) ? m->height : MapCanvas::kDefaultRoomHeight;
}
} // namespace

void MapCanvas::UpdateSizeForRoom() {
    int w = kDefaultRoomWidth;
    int h = kDefaultRoomHeight;
    if (m_levelData && m_activeRoomIndex >= 0 &&
        m_activeRoomIndex < (int)m_levelData->rooms.size()) {
        w = RoomWidthOf(m_levelData, m_models, m_activeRoomIndex);
        h = RoomHeightOf(m_levelData, m_models, m_activeRoomIndex);
    }
    // The canvas shows the room's playable rows only (no grey HUD band; the
    // game renders that below the cave but the editor doesn't display it).
    // Tile heights are scaled so the map keeps its on-screen 4:3 format.
    int cellH = CellHeightFor(m_tileSize, DisplayColumnsFor(w), h);
    setFixedSize(DisplayColumnsFor(w) * m_tileSize, h * cellH);
}

QColor MapCanvas::GetTileColor(int tileType, int tileY) const {
    if (!m_levelData) return QColor(30, 30, 30);

    switch (static_cast<hero::TileType>(tileType)) {
        case hero::TileType::AIR:
            return QColor(15, 15, 20);
        case hero::TileType::SOLID_WALL: {
            // Stripe: rows 0-3 use wall color 1, 4-7 wall color 2, 8-11 again
            // color 1 (mirrors the game kernel's 4-row band pattern).
            int band = tileY / 4;
            if (band % 2 == 1) {
                return QColor(m_levelData->wall2_r, m_levelData->wall2_g, m_levelData->wall2_b);
            }
            return QColor(m_levelData->wall_r, m_levelData->wall_g, m_levelData->wall_b);
        }
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
        case hero::TileType::HOT_ROCK_WALL:
            return QColor(255, 80, 20);
        default:
            return QColor(15, 15, 20);
    }
}

void MapCanvas::paintEvent(QPaintEvent* /*event*/) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // Canvas background
    painter.fillRect(rect(), QColor(10, 10, 15));

    hero::ModelData* model = nullptr;
    const hero::RoomData* room = nullptr;
    int roomWidth, roomHeight;

    if (m_modelMode) {
        // Model mode: show selected model directly
        if (!m_models || m_activeModelIndex < 0 || m_activeModelIndex >= (int)m_models->size()) {
            painter.setPen(Qt::white);
            painter.drawText(rect(), Qt::AlignCenter, "No Model Selected");
            return;
        }
        model = &(*m_models)[m_activeModelIndex];
        roomWidth = model->width;
        roomHeight = model->height;
    } else {
        // Level mode: show room's model + entities
        if (!m_levelData || m_activeRoomIndex < 0 || m_activeRoomIndex >= (int)m_levelData->rooms.size()) {
            painter.setPen(Qt::white);
            painter.drawText(rect(), Qt::AlignCenter, "No Room Loaded");
            return;
        }
        room = &m_levelData->rooms[m_activeRoomIndex];
        model = GetModelForRoom(m_levelData, m_models, m_activeRoomIndex);
        if (!model) {
            painter.setPen(Qt::white);
            painter.drawText(rect(), Qt::AlignCenter, "No Model");
            return;
        }
        roomWidth = RoomWidthOf(m_levelData, m_models, m_activeRoomIndex);
        roomHeight = RoomHeightOf(m_levelData, m_models, m_activeRoomIndex);
    }

    const int displayCols = DisplayColumnsFor(roomWidth);
    const int cellW = m_tileSize;
    const int cellH = CellHeightFor(m_tileSize, displayCols, roomHeight);

    // Render Grid & Tiles (full mirrored stage)
    for (int y = 0; y < roomHeight; ++y) {
        for (int dcol = 0; dcol < displayCols; ++dcol) {
            int x = MirrorColumn(dcol, roomWidth);
            int tileType = model->tiles[y * roomWidth + x];
            QRect tileRect(dcol * cellW, y * cellH, cellW, cellH);

            QColor color = GetTileColor(tileType, y);
            // Bottom band: air on last row shows the room's band COLUBK
            // (walls stay wall-colored — matches game: COLUBK only in open PF).
            if (room && room->bottom_band && y == roomHeight - 1 &&
                tileType == (int)hero::TileType::AIR) {
                color = QColor(room->bottom_r, room->bottom_g, room->bottom_b);
            }
            painter.fillRect(tileRect, color);

            painter.setPen(QColor(40, 40, 50));
            painter.drawRect(tileRect);

            if (tileType == (int)hero::TileType::FRAGILE_WALL) {
                painter.setPen(QColor(140, 90, 30));
                painter.drawLine(tileRect.topLeft(), tileRect.bottomRight());
            } else if (tileType == (int)hero::TileType::REINFORCED_WALL) {
                painter.setPen(QColor(220, 80, 80));
                painter.drawRect(tileRect.adjusted(3, 3, -3, -3));
            }
        }
    }

    // Draw seam marker at mirror axis
    int seamX = roomWidth * m_tileSize;
    int canvasHeight = roomHeight * cellH;
    painter.setPen(QPen(QColor(90, 90, 110), 2));
    painter.drawLine(seamX, 0, seamX, canvasHeight);

    // In level mode, render entities and miner
    if (!m_modelMode && room && m_levelData) {
        // Render Miner Goal position if in this room
        if (m_levelData->miner_room == m_activeRoomIndex) {
            int mx = (int)(m_levelData->miner_x * cellW);
            int my = (int)(m_levelData->miner_y * cellH);
            QRect minerRect(mx - 12, my - 12, 24, 24);

            painter.setBrush(QColor(255, 140, 180));
            painter.setPen(Qt::black);
            painter.drawEllipse(minerRect);
            painter.drawText(minerRect, Qt::AlignCenter, "M");
        }

        // Render Lamps in room
        for (const auto& lamp : room->lamps) {
            int lx = (int)(lamp.x * cellW);
            int ly = (int)(lamp.y * cellH);
            int bulbSize = 12;

            painter.setBrush(lamp.lit ? QColor(255, 230, 80) : QColor(110, 110, 110));
            painter.setPen(Qt::black);
            painter.drawEllipse(lx - bulbSize / 2, ly - bulbSize, bulbSize, bulbSize);

            painter.setPen(QColor(150, 150, 150));
            painter.drawLine(lx, ly, lx, ly + 10);
            painter.setBrush(QColor(120, 120, 120));
            painter.drawRect(lx - 5, ly + 10, 10, 3);

            painter.setPen(Qt::black);
            painter.drawText(QRect(lx - 10, ly - bulbSize - 14, 20, 14), Qt::AlignCenter, "L");
        }

        // Render Enemies in room
        for (const auto& enemy : room->enemies) {
            int ex = (int)(enemy.x * cellW);
            int ey = (int)(enemy.y * cellH);
            int markerSize = qMax(12, m_tileSize - 6);
            QRect enemyRect(ex + (cellW - markerSize) / 2,
                            ey + (cellH - markerSize) / 2,
                            markerSize, markerSize);

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
            DrawFacingArrow(painter, enemyRect, enemy.dir);
        }
    } // end level-mode entity rendering
}

void MapCanvas::DrawFacingArrow(QPainter& painter, const QRect& enemyRect, int dir) const {
    // White triangle beside the marker: tip points the way the enemy faces.
    const int cy = enemyRect.center().y();
    const int halfH = enemyRect.height() / 3;
    QPolygonF tri;
    if (dir >= 0) {
        const int tipX = enemyRect.right() + 9;
        const int baseX = enemyRect.right() + 2;
        tri << QPointF(tipX, cy)
            << QPointF(baseX, cy - halfH)
            << QPointF(baseX, cy + halfH);
    } else {
        const int tipX = enemyRect.left() - 9;
        const int baseX = enemyRect.left() - 2;
        tri << QPointF(tipX, cy)
            << QPointF(baseX, cy - halfH)
            << QPointF(baseX, cy + halfH);
    }
    painter.setBrush(QColor(255, 255, 255));
    painter.setPen(QPen(QColor(20, 20, 20), 1));
    painter.drawPolygon(tri);
}

int MapCanvas::CountRoomElements() const {
    if (!m_levelData || m_activeRoomIndex < 0 ||
        m_activeRoomIndex >= (int)m_levelData->rooms.size())
        return 0;
    const hero::RoomData& room = m_levelData->rooms[m_activeRoomIndex];
    int n = (int)room.enemies.size() + (int)room.lamps.size();
    if (m_levelData->miner_room == m_activeRoomIndex) n++;
    const hero::ModelData* model =
        GetModelForRoom(const_cast<hero::LevelData*>(m_levelData),
                        const_cast<std::vector<hero::ModelData>*>(m_models),
                        m_activeRoomIndex);
    if (model) {
        for (int t : model->tiles) {
            if (t == (int)hero::TileType::RAFT || t == (int)hero::TileType::MAGMA_FALL)
                n++;
        }
    }
    return n;
}

bool MapCanvas::AllowAddElement() {
    if (CountRoomElements() < kMaxRoomElements) return true;
    QMessageBox::warning(
        nullptr, QObject::tr("Element Limit"),
        QObject::tr("Maximum of 3 elements per room (miner, enemies, lamps, raft, magma, ...).\n"
                    "Restricting the number of elements to avoid too much flicker."));
    return false;
}

bool MapCanvas::ElementInRow(int tileY) const {
    if (!m_levelData || m_activeRoomIndex < 0 ||
        m_activeRoomIndex >= (int)m_levelData->rooms.size())
        return false;
    const hero::RoomData& room = m_levelData->rooms[m_activeRoomIndex];
    for (const auto& e : room.enemies) {
        if ((int)std::floor(e.y) == tileY) return true;
    }
    for (const auto& lamp : room.lamps) {
        if ((int)std::floor(lamp.y) == tileY) return true;
    }
    if (m_levelData->miner_room == m_activeRoomIndex &&
        (int)std::floor(m_levelData->miner_y) == tileY)
        return true;
    return false;
}

bool MapCanvas::AllowElementInRow(int tileY, int ignoreY) {
    if (tileY == ignoreY) return true;
    if (!ElementInRow(tileY)) return true;
    QMessageBox::warning(
        nullptr, QObject::tr("Row Limit"),
        QObject::tr("Only one element (miner, enemy, lamp) allowed per row.\n"
                    "This helps eliminate flicker in the game."));
    return false;
}

void MapCanvas::ApplyBrushAt(int tileX, int entityX, int tileY) {
    hero::ModelData* model = nullptr;
    hero::RoomData* room = nullptr;

    if (m_modelMode) {
        // Model mode: edit selected model directly
        if (!m_models || m_activeModelIndex < 0 || m_activeModelIndex >= (int)m_models->size()) return;
        model = &(*m_models)[m_activeModelIndex];
    } else {
        // Level mode: edit through room's model
        if (!m_levelData || m_activeRoomIndex < 0 || m_activeRoomIndex >= (int)m_levelData->rooms.size()) return;
        room = &m_levelData->rooms[m_activeRoomIndex];
        model = GetModelForRoom(m_levelData, m_models, m_activeRoomIndex);
        if (!model) return;
    }

    int roomWidth = model->width;
    int roomHeight = model->height;
    int displayColumns = DisplayColumnsFor(roomWidth);

    if (tileX < 0 || tileX >= roomWidth || tileY < 0 || tileY >= roomHeight) return;

    int brushVal = static_cast<int>(m_currentBrush);

    if (m_currentBrush == BrushTool::SOLID_WALL || m_currentBrush == BrushTool::ERASE_AIR ||
        m_currentBrush == BrushTool::HOT_ROCK_WALL) {
        model->tiles[tileY * roomWidth + tileX] = brushVal;
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::ADD_RAFT) {
        int idx = tileY * roomWidth + tileX;
        if (model->tiles[idx] != (int)hero::TileType::RAFT && room && !AllowAddElement()) return;
        model->tiles[idx] = (int)hero::TileType::RAFT;
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::ADD_MAGMA) {
        int idx = tileY * roomWidth + tileX;
        if (model->tiles[idx] != (int)hero::TileType::MAGMA_FALL && room && !AllowAddElement()) return;
        model->tiles[idx] = (int)hero::TileType::MAGMA_FALL;
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::SET_MINER_GOAL) {
        if (m_levelData->miner_room != m_activeRoomIndex && !AllowAddElement()) return;
        // Same room: ignore miner's current row (re-place frees it first).
        int ignoreY = (m_levelData->miner_room == m_activeRoomIndex)
                          ? (int)std::floor(m_levelData->miner_y)
                          : -1;
        if (!AllowElementInRow(tileY, ignoreY)) return;
        m_levelData->miner_room = m_activeRoomIndex;
        m_levelData->miner_x = (float)tileX + 0.5f;
        m_levelData->miner_y = (float)tileY;
        emit levelModified();
        update();
    } else if (!m_modelMode && room && (m_currentBrush == BrushTool::ADD_SPIDER || m_currentBrush == BrushTool::ADD_BAT ||
               m_currentBrush == BrushTool::ADD_SNAKE || m_currentBrush == BrushTool::ADD_TENTACLE ||
               m_currentBrush == BrushTool::ADD_MOTH)) {
        // Entity placement: full stage width, no mirroring. Reject the HUD
        // band (tileY >= roomHeight) so enemies can't spawn beneath the cave.
        if (entityX < 0 || entityX >= displayColumns ||
            tileY < 0 || tileY >= roomHeight) return;

        hero::EnemyData eData;
        if (m_currentBrush == BrushTool::ADD_SPIDER) eData.type = (int)hero::EnemyType::SPIDER;
        else if (m_currentBrush == BrushTool::ADD_BAT) eData.type = (int)hero::EnemyType::BAT;
        else if (m_currentBrush == BrushTool::ADD_SNAKE) eData.type = (int)hero::EnemyType::SNAKE;
        else if (m_currentBrush == BrushTool::ADD_TENTACLE) eData.type = (int)hero::EnemyType::TENTACLE;
        else if (m_currentBrush == BrushTool::ADD_MOTH) eData.type = (int)hero::EnemyType::GIANT_MOTH;

        eData.x = (float)entityX;
        eData.y = (float)tileY;
        eData.range_min = (float)std::max(0, entityX - 3);
        eData.range_max = (float)std::min(displayColumns - 1, entityX + 3);
        eData.speed = 1.5f;
        eData.dir = m_initialFacing;

        // Occupied tile: flip existing enemy facing instead of stacking.
        for (auto& e : room->enemies) {
            if ((int)std::floor(e.x) == entityX && (int)std::floor(e.y) == tileY) {
                e.dir = (e.dir >= 0) ? -1 : 1;
                emit levelModified();
                update();
                return;
            }
        }

        if (!AllowElementInRow(tileY)) return;
        if (!AllowAddElement()) return;
        room->enemies.push_back(eData);
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::ADD_LAMP) {
        // Entity placement: full stage width, no mirroring. No lamps in the HUD band.
        if (entityX < 0 || entityX >= displayColumns ||
            tileY < 0 || tileY >= roomHeight) return;

        // Replace any lamp already on this tile, otherwise add a new one
        for (auto& lamp : room->lamps) {
            if ((int)std::floor(lamp.x) == entityX && (int)std::floor(lamp.y) == tileY) {
                lamp.x = (float)entityX + 0.5f;
                lamp.y = (float)tileY + 0.5f;
                lamp.lit = true;
                emit levelModified();
                update();
                return;
            }
        }

        if (!AllowElementInRow(tileY)) return;
        if (!AllowAddElement()) return;
        hero::LampData lamp;
        lamp.x = (float)entityX + 0.5f;
        lamp.y = (float)tileY + 0.5f;
        lamp.lit = true;
        room->lamps.push_back(lamp);
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::DELETE_ENTITY) {
        // Entities live in full stage coordinates (no mirroring)
        for (auto it = room->enemies.begin(); it != room->enemies.end(); ++it) {
            if ((int)std::floor(it->x) == entityX && (int)std::floor(it->y) == tileY) {
                room->enemies.erase(it);
                emit levelModified();
                update();
                return;
            }
        }
        for (auto it = room->lamps.begin(); it != room->lamps.end(); ++it) {
            if ((int)std::floor(it->x) == entityX && (int)std::floor(it->y) == tileY) {
                room->lamps.erase(it);
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

void MapCanvas::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_F) {
        m_initialFacing = -m_initialFacing;
        emit facingChanged(m_initialFacing);
        update();
        event->accept();
        return;
    }
    QWidget::keyPressEvent(event);
}

void MapCanvas::MouseToTile(const QPointF& pos, bool apply) {
    int roomWidth = kDefaultRoomWidth;
    int roomHeight = kDefaultRoomHeight;
    if (m_levelData && m_activeRoomIndex >= 0 &&
        m_activeRoomIndex < (int)m_levelData->rooms.size()) {
        roomWidth = RoomWidthOf(m_levelData, m_models, m_activeRoomIndex);
        roomHeight = RoomHeightOf(m_levelData, m_models, m_activeRoomIndex);
    }

    int cellH = CellHeightFor(m_tileSize, DisplayColumnsFor(roomWidth), roomHeight);
    int displayCol = (int)(pos.x() / m_tileSize);
    int tileX = MirrorColumn(displayCol, roomWidth);
    int tileY = (int)(pos.y() / cellH);
    emit mouseMovedToTile(tileX, tileY);
    if (apply)
        // tileX is the mirrored room column for tiles; displayCol is the raw
        // full-stage column (0..2*width-1) used by ApplyBrushAt for entities.
        ApplyBrushAt(tileX, displayCol, tileY);
}

void MapCanvas::SetActiveModel(int modelIndex) {
    m_activeModelIndex = modelIndex;
    update();
}

} // namespace editor
