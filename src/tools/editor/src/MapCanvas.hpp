/*
 * Savior AI - Level Editor
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
    DELETE_ENTITY = 18,
    // Model tab: D6 asymmetric patch on the RIGHT half (wall where the
    // mirror is open; toggle with a second click). One right_col per model
    // (single ball-x envelope — convert hard-fails mixed columns).
    ASYM_PATCH = 19,
    // Level tab: the collectible key (EnemyType::KEY = 6, counts toward
    // kMaxRoomElements like every other object).
    ADD_KEY = 20,
    // Model tab: new feature brushes (BrushTool-local values 21-24 — 9..19
    // are taken; ApplyBrushAt maps them to TileType 9-12).
    DOOR_TILE = 21,     // TileType::LOCKED_DOOR as an async side-0 patch
    PHASE_TILE = 22,    // TileType::PHASE grid cell
    HCRUNCH_TILE = 23,  // TileType::HCRUNCH grid cell
    // Level tab: the power cell (EnemyType::POWER_CELL = 14) - refills the timer.
    ADD_CELL = 24,
    // Level tab: an extra miner to rescue (EnemyType::EXTRA_MINER = 15).
    ADD_MINER2 = 25
};

class MapCanvas : public QWidget {
    Q_OBJECT

public:
    explicit MapCanvas(QWidget* parent = nullptr);

    // Fallback size used until a room is loaded.
    static constexpr int kDefaultRoomWidth = 10;  // D7 grid (cells/half)
    static constexpr int kDefaultRoomHeight = 4;   // 36-scanline color bands
                                                   // (N=4: keep in step with
                                                   // hero::kRoomHeight)

    void SetLevelData(hero::LevelData* levelData, std::vector<hero::ModelData>* models, int activeRoomIndex);
    void SetActiveRoom(int roomIndex);
    void SetTileSize(int size);
    int TileSize() const { return m_tileSize; }
    void SetCurrentBrush(BrushTool brush) { m_currentBrush = brush; }
    void SetEditMode(bool modelMode) { m_modelMode = modelMode; update(); }
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
    void mouseReleaseEvent(QMouseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

public:
    // Brush entry point (the mouse handlers are thin wrappers). Public so the
    // headless --brushtest can drive the real brush logic — the room-level
    // async relocation (2026-10-18) has no other automated coverage.
    void ApplyBrushAt(int tileX, int entityX, int tileY);

private:
    // Drag & drop of placed objects (level mode). An object is picked by its
    // real sprite rectangle; it follows the mouse snapped to the positions the
    // ROM can draw (whole display columns, 9 px rows, no wall under the 8 px
    // sprite - the snake is the only one allowed in walls).
    enum class EntKind { None, Enemy, Lamp, Miner };
    struct Geo {
        const hero::ModelData* model = nullptr;
        hero::RoomData* room = nullptr;
        int rw = 0, rh = 0, cols = 0, rows = 0, cellW = 0, cellH = 0;
        double pxH = 0;   // canvas pixels per game scanline
    };
    bool GetGeo(Geo& g) const;
    QRectF EntityRect(EntKind kind, int idx) const;
    bool LampWallOnRight(int idx) const;
    bool PlacementOk(EntKind kind, int idx, int type, int col, int tileY) const;
    bool TryBeginDrag(const QPointF& pos);
    void DragTo(const QPointF& pos);

    EntKind m_dragKind = EntKind::None;
    int m_dragIdx = -1;
    int m_dragGrabCol = 0;
    int m_dragGrabRow = 0;
    bool m_dragMoved = false;
    QPointF m_dragPress;

    void MouseToTile(const QPointF& pos, bool apply);
    // Warn (once per mouse RELEASE, never mid-drag) about feature layouts
    // convert would reject at build: phase on the hot middle band,
    // hcrunch cells outside one band / not a contiguous prefix from col 0.
    void ValidateFeatureTiles();
    // The room that owns the async layer being edited/drawn (the ACTIVE room
    // in level mode; NULL in model mode, where the async brushes refuse).
    const hero::RoomData* AsyncRoomRef() const;
    // Async walls (door/phase/hcrunch) are ROOM properties since the
    // 2026-10-17 format change; the room-level brush UI is the next editor
    // step. The legacy brushes refuse (one dialog per session) instead of
    // writing the retired model fields.
    void WarnAsyncBrushNeedsRoomEditor();
    QColor GetTileColor(int tileType, int tileY) const;
    void UpdateSizeForRoom();
    void DrawFacingArrow(QPainter& painter, const QRect& enemyRect, int dir,
                         bool vertical = false) const;
    // Miner + enemies + lamps in the active room (flicker budget).
    int CountRoomElements() const;
    // Same count for an explicit room index (crunch rule scans every room
    // that shares a model).
    int CountRoomElementsIn(int roomIdx) const;
    // True if the ACTIVE ROOM has an hcrunch feature cell.
    bool RoomHasCrunch() const;
    // False + warning dialog if adding would exceed kMaxRoomElements.
    // asEnemy=true relaxes the door-room cap (a door room allows a single
    // enemy); every other element kind stays blocked in a door room.
    bool AllowAddElement(bool asEnemy = false);
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
    // Hard cap 2 objects/room (2026-10-02, user rule): laser + bomb runs
    // pushed 3-object rooms over the frame budget (screen jump flicker).
    static constexpr int kMaxRoomElements = 2;
    // Game darkness mask = 8 bits (rooms 0-7; EnemyRamD + LaserState).
    // Lamps in rooms >= 8 would never darken — refuse placement there.
    static constexpr int kDarkMaskRooms = 8;
};

} // namespace editor
