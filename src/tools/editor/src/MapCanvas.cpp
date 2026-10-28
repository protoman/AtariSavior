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

#include "MapCanvas.hpp"
#include "TileColors.hpp"
#include <QPainter>
#include <QMouseEvent>
#include <QKeyEvent>
#include <QMessageBox>
#include <QPolygonF>
#include <QStringList>
#include <algorithm>
#include <cmath>
#include <cstdint>

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

// Full-stage display columns (4px each): D7 cells are 8px = 2 display cols
// per model cell, both halves -> width*4 (10 cells/half -> 40 cols, the
// game's stage). Pre-D7 (1 col/cell) was width*2.
static int DisplayColumnsFor(int roomWidth) { return roomWidth * 4; }

// OBJECT Y (user report 2026-10-26: a power cell clicked in band 2 was drawn in
// the floor of band 3 by the game). The canvas draws `displayRows` = 4 rows per
// band (16 for a four-band room), but the stage data - convert_level, the
// generator, the kernel - counts 12-px DISPLAY rows: 12 over the 144-px cave, 3
// per band on a four-band room. Enemies, lamps and the miner therefore store
// canvas_row * 12 / displayRows (a canvas row is 9 px there) and are read back
// through RowOfY. A three-band room has 12 canvas rows, so nothing changes.
static float YOfRow(int row, int displayRows) {
    return (float)row * 12.0f / (float)displayRows;
}
static int RowOfY(float y, int displayRows) {
    return (int)std::floor(y * (float)displayRows / 12.0f + 1e-3f);
}

// display col -> MODEL cell index (0..width-1), left-frame. Left half =
// first width*2 display cols; right half mirrors pixel-wise (39-dcol),
// then the 2-cols-per-cell pair collapses via >>1.
static int MirrorColumn(int displayCol, int roomWidth) {
    int displayCols = DisplayColumnsFor(roomWidth);
    int half = displayCols / 2;
    int src = (displayCol < half) ? displayCol : (displayCols - 1 - displayCol);
    return src >> 1;
}

// Special-feature presence bits for a ROOM (user rule 2026-10-14: door,
// phase, hcrunch are ALONE per room). Async lives on the ROOM since
// the 2026-10-17 format change — 1=door (LOCKED_DOOR strip), 2=phase,
// 8=hcrunch (the room's feature cells).
static int RoomSpecialBits(const hero::RoomData& r) {
    int bits = 0;
    for (const auto& c : r.feature_cells) {
        if (c.size() < 3) continue;
        if (c[2] == (int)hero::TileType::PHASE) bits |= 2;
        else if (c[2] == (int)hero::TileType::HCRUNCH) bits |= 8;
    }
    for (const auto& p : r.asym_patches) {
        if (p.size() >= 3 && p[2] == (int)hero::TileType::LOCKED_DOOR)
            bits |= 1;
    }
    return bits;
}

// Room feature cell at (row, col): TileType::PHASE/HCRUNCH or -1.
static int FindFeature(const hero::RoomData& r, int row, int col) {
    for (const auto& c : r.feature_cells) {
        if (c.size() >= 3 && c[0] == row && c[1] == col) return c[2];
    }
    return -1;
}

// Patch lookup: [row, col, tile] (right/ball, legacy = side 0) or
// [row, col, tile, side] (side 0 = right/ball, 1 = left/M1); col is the
// half's own cell index. Returns index or -1.
static int FindPatch(const hero::RoomData& r, int row, int col, int side) {
    for (int i = 0; i < (int)r.asym_patches.size(); ++i) {
        const auto& p = r.asym_patches[i];
        if ((int)p.size() < 3) continue;
        const int pside = (int)p.size() == 4 ? p[3] : 0;
        if (p[0] == row && p[1] == col && pside == side) return i;
    }
    return -1;
}

// Port of convert_room.find_rectangles (solids "#HPVC") — greedy scan,
// extend right then down, thin (w==1) stops before a row that joins a
// wider run. Returns the rect count (the budget is what matters here).
static int CountRightRects(const std::vector<std::string>& rows) {
    int height = (int)rows.size();
    int width = height ? (int)rows[0].size() : 0;
    std::vector<std::vector<bool>> visited(
        height, std::vector<bool>(width, false));
    auto solid = [&](int r, int c) {
        const char ch = rows[r][c];
        return ch == '#' || ch == 'H' || ch == 'P' || ch == 'V' || ch == 'C';
    };
    int count = 0;
    for (int row = 0; row < height; ++row) {
        for (int col = 0; col < width; ++col) {
            if (!solid(row, col) || visited[row][col]) continue;
            int w = 1;
            while (col + w < width && solid(row, col + w) &&
                   !visited[row][col + w])
                ++w;
            int h = 1;
            while (row + h < height) {
                bool ok = true;
                for (int c = col; c < col + w; ++c) {
                    if (!solid(row + h, c) || visited[row + h][c]) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) break;
                if (w == 1) {
                    const bool left = col > 0 && solid(row + h, col - 1);
                    const bool right = col + 1 < width && solid(row + h, col + 1);
                    if (left || right) break;
                }
                ++h;
            }
            for (int r = row; r < row + h; ++r)
                for (int c = col; c < col + w; ++c) visited[r][c] = true;
            ++count;
        }
    }
    return count;
}

// Resolved right rows exactly like convert_level.resolve_asym_patches:
// mirror of the left rows (chars like tile_to_char), side-0 patches on
// top. Empty = no patches at all (plain mirror, no WallMask budget).
static std::vector<std::string> BuildRightRows(const hero::ModelData& m,
                                               const hero::RoomData& r) {
    if (r.asym_patches.empty()) return {};
    const int w = m.width, h = m.height;
    std::vector<std::string> left(h, std::string(w, '.'));
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x)
            if (m.tiles[y * w + x] != (int)hero::TileType::AIR)
                left[y][x] = '#';         // shape only (features are room cells)
    }
    // The room's feature cells are solid too (convert: solids "#HPV") and the
    // right half mirrors them, so they count toward the WallMask budget.
    for (const auto& c : r.feature_cells) {
        if (c.size() >= 3 && c[0] >= 0 && c[0] < h && c[1] >= 0 && c[1] < w)
            left[c[0]][c[1]] = '#';
    }
    std::vector<std::string> right(h, std::string(w, '.'));
    for (int y = 0; y < h; ++y)
        for (int k = 0; k < w; ++k) right[y][k] = left[y][w - 1 - k];
    for (const auto& p : r.asym_patches) {
        if ((int)p.size() < 3) continue;
        const int side = (int)p.size() == 4 ? p[3] : 0;
        if (side != 0) continue;
        const int row = p[0], col = p[1];
        if (row < 0 || row >= h || col < 0 || col >= w) continue;
        right[row][col] = (p[2] == (int)hero::TileType::AIR) ? '.' : '#';
    }
    return right;
}

// WallMask budget (BombPacked b3-6 — Risk 1): only 4 right-half rects can
// be maskable; convert hard-fails above that. *outCount = found count (0
// when no patches = no budget). Editor pre-flight so the brush blocks the
// paint that would brick the build.
static bool RightRectsOk(const hero::ModelData& m, const hero::RoomData& r,
                         int* outCount) {
    const auto rows = BuildRightRows(m, r);
    if (rows.empty()) { *outCount = 0; return true; }
    *outCount = CountRightRects(rows);
    return *outCount <= 4;
}

static void WarnRightRectBudget(int n) {
    QMessageBox::warning(
        nullptr, QObject::tr("WallMask Budget"),
        QObject::tr("Blocked: this paint would split the right half into "
                    "%1 wall rectangles — the budget is 4 (WallMask "
                    "b3-6, only 4 bomb-destroy bits; convert hard-fails "
                    "this too).\nMerge the wall blocks (paint the gap "
                    "between them) or erase the stray cell.").arg(n));
}

// Tile height so the whole visible map (DisplayColumnsFor(roomWidth) columns x
// roomHeight rows) renders at a 4:3 aspect, matching its proportions on the
// game screen. Cells are therefore rectangles, not squares.
static int CellHeightFor(int cellWidth, int displayCols, int roomHeight) {
    if (roomHeight <= 0 || displayCols <= 0) return cellWidth;
    return std::max(1, (int)std::lround(cellWidth * (double)displayCols * 3.0 /
                                        (double)(roomHeight * 4)));
}

// ROM sprite art (kernel.asm ObjSprites), bit 7 = leftmost px, one row per
// scanline. Keep in step with that table.
struct SpriteArt { const uint8_t* rows; int n; };
#define ART(name, ...) \
    static const uint8_t name##Rows[] = {__VA_ARGS__}; \
    static const SpriteArt name = {name##Rows, (int)sizeof name##Rows};
ART(kKeyArt, 0x3C,0x42,0x5A,0x42,0x3C,0x18,0x18,0x18,0x18,0x1C,0x18,0x10)
ART(kCellArt, 0x7E,0xA5,0xA5,0x7E)
ART(kMothArt, 0x24,0x42,0x66,0xE7,0xFF,0x7E,0x3C,0x18,0x3C,0x7E,0xFF,0xE7,0x66,0x24)
ART(kSpiderArt, 0xA5,0xA5,0xA5,0x5A,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C,0x7E,0x7E,0x3C,0x5A,0xA5)
ART(kTentArt, 0x1C,0x22,0x24,0x18,0x0C,0x14,0x18,0x28,0x30,0x50,0x70,0xFC,0xFF,0xBD)
ART(kBatArt, 0x81,0xC3,0x66,0x24,0x3C,0x7E,0xFF,0x99,0x18,0x24)
ART(kSnakeArt, 0x06,0x0F,0xF8,0xF8,0x0F,0x06)
ART(kMinerArt, 0x30,0x38,0x32,0x6C,0xF0,0xE0,0xFC,0x76,0x3F)
ART(kRaftArt, 0xFF,0xFF)
ART(kLampArt, 0xFC,0xFC,0x18,0x18,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C)
ART(kLampRArt, 0x3F,0x3F,0x18,0x18,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C)
#undef ART

static SpriteArt EnemyArt(int type) {
    switch (static_cast<hero::EnemyType>(type)) {
        case hero::EnemyType::SPIDER: return kSpiderArt;
        case hero::EnemyType::BAT: return kBatArt;
        case hero::EnemyType::SNAKE: return kSnakeArt;
        case hero::EnemyType::TENTACLE: return kTentArt;
        case hero::EnemyType::GIANT_MOTH: return kMothArt;
        case hero::EnemyType::RAFT: return kRaftArt;
        case hero::EnemyType::POWER_CELL: return kCellArt;
        case hero::EnemyType::EXTRA_MINER: return kMinerArt;
        default: return kKeyArt;
    }
}

// Tiles the playfield draws over a sprite (convert's "#H" cells + features).
static bool IsWallTile(int t) {
    return t == (int)hero::TileType::SOLID_WALL ||
           t == (int)hero::TileType::FRAGILE_WALL ||
           t == (int)hero::TileType::REINFORCED_WALL ||
           t == (int)hero::TileType::HOT_ROCK_WALL ||
           t == (int)hero::TileType::PHASE ||
           t == (int)hero::TileType::HCRUNCH;
}

MapCanvas::MapCanvas(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);  // F toggles initial facing
    // Default 20x3 stage until a room is loaded. The map area only: the grey
    // HUD band is drawn by the game kernel and is not shown/edited here.
    setFixedSize(DisplayColumnsFor(kDefaultRoomWidth) * m_tileSize,
                 kDefaultRoomHeight * 4 * CellHeightFor(m_tileSize,
                     DisplayColumnsFor(kDefaultRoomWidth), kDefaultRoomHeight * 4));
}

// The room that owns the async layer being edited/drawn: the ACTIVE room in
// level mode; NULL in model mode (the model tab has no room context, and the
// async brushes refuse there).
const hero::RoomData* MapCanvas::AsyncRoomRef() const {
    if (m_modelMode || !m_levelData) return nullptr;
    if (m_activeRoomIndex < 0 ||
        m_activeRoomIndex >= (int)m_levelData->rooms.size())
        return nullptr;
    return &m_levelData->rooms[m_activeRoomIndex];
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
    int displayRows = h * 4;
    int cellH = CellHeightFor(m_tileSize, DisplayColumnsFor(w), displayRows);
    setFixedSize(DisplayColumnsFor(w) * m_tileSize, displayRows * cellH);
}

QColor MapCanvas::GetTileColor(int tileType, int tileY) const {
    if (!m_levelData) return QColor(30, 30, 30);
    return editor::TileColor(
        tileType, tileY,
        QColor(m_levelData->wall_r, m_levelData->wall_g, m_levelData->wall_b),
        QColor(m_levelData->wall2_r, m_levelData->wall2_g, m_levelData->wall2_b));
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
    const int displayRows = roomHeight * 4;
    const int cellH = CellHeightFor(m_tileSize, displayCols, displayRows);

    // Render Grid & Tiles (full mirrored stage + painted asym patches)
    const int half = displayCols / 2;
    for (int y = 0; y < displayRows; ++y) {
        for (int dcol = 0; dcol < displayCols; ++dcol) {
            int x = MirrorColumn(dcol, roomWidth);
            int modelY = y / 4;
            int tileType = model->tiles[modelY * roomWidth + x];
            // Right half: a painted patch overrides the mirror (wall where
            // the mirror is open); left half: an M1 patch paints wall color
            // over an open cell. Both draw with a cyan outline so patches
            // read as patches, not mirrored walls.
            bool patch = false;
            bool doorPatch = false;
            const hero::RoomData* ar = AsyncRoomRef();
            if (ar) {
                if (dcol >= half) {
                    int rc = (dcol - half) >> 1;
                    int pi = FindPatch(*ar, modelY, rc, 0);
                    patch = pi >= 0;
                    doorPatch = patch &&
                        (int)ar->asym_patches[pi].size() >= 3
                        && ar->asym_patches[pi][2]
                               == (int)hero::TileType::LOCKED_DOOR;
                } else {
                    int pi = FindPatch(*ar, modelY, x, 1);
                    patch = pi >= 0;
                    doorPatch = patch &&
                        (int)ar->asym_patches[pi].size() >= 3
                        && ar->asym_patches[pi][2]
                               == (int)hero::TileType::LOCKED_DOOR;
                }
                // The room's feature cells paint their own colour (the model
                // grid holds the shape, not the behaviour).
                const int feat = FindFeature(*ar, modelY, x);
                if (feat >= 0 && dcol < half) tileType = feat;
            }
            if (patch)
                tileType = doorPatch ? (int)hero::TileType::LOCKED_DOOR
                                     : (int)hero::TileType::SOLID_WALL;
            QRect tileRect(dcol * cellW, y * cellH, cellW, cellH);

            QColor color = GetTileColor(tileType, modelY);
            // Middle band (row 1): the model's mid_band_type selector makes
            // every wall there hot (convert promotes row 1 to 'H' the same
            // way — the legacy HOT_ROCK tile value is gone as a brush).
            // Feature tiles keep their own color (convert keeps their
            // P/C chars even on the hot band — hot+phase is rejected
            // in ValidateFeatureTiles, hcrunch is allowed).
            const bool featureTile =
                tileType == (int)hero::TileType::PHASE ||
                tileType == (int)hero::TileType::HCRUNCH ||
                tileType == (int)hero::TileType::LOCKED_DOOR;
            if (model->mid_band_type != 0 && modelY == 1 &&
                tileType != (int)hero::TileType::AIR && !featureTile) {
                color = GetTileColor((int)hero::TileType::HOT_ROCK_WALL, modelY);
            }
            // Bottom band: air on last row shows the room's band COLUBK
            // (walls stay wall-colored — matches game: COLUBK only in open PF).
            // The game draws the water only as the band's LAST 12 of 36 scanlines
            // (the tide moves it 0-3 lines); above it the band is open air that
            // a raft floats in. So: the band's last canvas row is water, the
            // row above it only in its lower third.
            const bool waterCell = room && room->bottom_band &&
                modelY == roomHeight - 1 &&
                tileType == (int)hero::TileType::AIR;
            const QColor waterColor = waterCell
                ? QColor(room->bottom_r, room->bottom_g, room->bottom_b) : color;
            if (waterCell && (y % 4) == 3) {
                color = waterColor;
            }
            painter.fillRect(tileRect, color);
            if (waterCell && (y % 4) == 2) {
                painter.fillRect(tileRect.x(), tileRect.y() + tileRect.height() * 2 / 3,
                                 tileRect.width(), tileRect.height() - tileRect.height() * 2 / 3,
                                 waterColor);
            }

            // D7 grid: one model cell = 2 display cols, so the grid border
            // and per-cell decorations are drawn once per cell (even dcol =
            // cell start on both halves; the right half mirrors 39-dcol),
            // not once per display col — that made the grid look like the
            // old pre-D7 40-col layout.
            if ((dcol & 1) == 0) {
                QRect cellRect(dcol * cellW, y * cellH, cellW * 2, cellH);
                painter.setPen(QColor(40, 40, 50));
                painter.drawRect(cellRect);
                if (patch) {
                    painter.setPen(QPen(QColor(0, 210, 255), 2));
                    painter.drawRect(cellRect);
                }

                if (tileType == (int)hero::TileType::FRAGILE_WALL) {
                    painter.setPen(QColor(140, 90, 30));
                    painter.drawLine(cellRect.topLeft(), cellRect.bottomRight());
                } else if (tileType == (int)hero::TileType::REINFORCED_WALL) {
                    painter.setPen(QColor(220, 80, 80));
                    painter.drawRect(cellRect.adjusted(3, 3, -3, -3));
                }
            }
        }
    }

    // Draw seam marker at mirror axis
    int seamX = half * m_tileSize;
    int canvasHeight = displayRows * cellH;
    painter.setPen(QPen(QColor(90, 90, 110), 2));
    painter.drawLine(seamX, 0, seamX, canvasHeight);

    // In level mode, render entities and miner
    if (!m_modelMode && room && m_levelData) {
        // Objects are drawn as the REAL ROM sprite (kernel.asm ObjSprites):
        // 8 game px wide from the column's left edge (1 px per bit, so two
        // 4 px display columns - an odd column straddles two wall cells),
        // 1 scanline per row. The dotted box is the full 8 px window.
        auto drawSprite = [&](const QRectF& r, const SpriteArt& art,
                              const QColor& color, const QString& label) {
            const double pxW = r.width() / 8.0;
            const double pxH = r.height() / art.n;
            painter.setPen(QPen(color, 1, Qt::DotLine));
            painter.setBrush(Qt::NoBrush);
            painter.drawRect(r);
            painter.setPen(Qt::NoPen);
            painter.setBrush(color);
            for (int row = 0; row < art.n; ++row)
                for (int bit = 0; bit < 8; ++bit)
                    if (art.rows[row] & (0x80 >> bit))
                        painter.drawRect(QRectF(r.x() + bit * pxW,
                                                r.y() + row * pxH,
                                                pxW + 0.5, pxH + 0.5));
            painter.setPen(Qt::black);
            painter.drawText(r, Qt::AlignCenter, label);
        };

        // Render Miner Goal position if in this room
        if (m_levelData->miner_room == m_activeRoomIndex) {
            const QRectF mr = EntityRect(EntKind::Miner, 0);
            drawSprite(mr, kMinerArt, QColor(255, 140, 180), "M");
            DrawFacingArrow(painter, mr.toRect(), m_levelData->miner_dir);
        }

        // Render Lamps in room
        for (int i = 0; i < (int)room->lamps.size(); ++i) {
            const auto& lamp = room->lamps[i];
            drawSprite(EntityRect(EntKind::Lamp, i),
                       LampWallOnRight(i) ? kLampRArt : kLampArt,
                       lamp.lit ? QColor(255, 230, 80) : QColor(110, 110, 110),
                       "L");
        }

        // Render Enemies in room
        for (int i = 0; i < (int)room->enemies.size(); ++i) {
            const auto& enemy = room->enemies[i];
            QColor eColor;
            QString label;
            switch (static_cast<hero::EnemyType>(enemy.type)) {
                case hero::EnemyType::SPIDER: eColor = QColor(240, 200, 0); label = "S"; break;
                case hero::EnemyType::BAT: eColor = QColor(220, 40, 60); label = "B"; break;
                case hero::EnemyType::SNAKE: eColor = QColor(40, 200, 40); label = "K"; break;
                case hero::EnemyType::TENTACLE: eColor = QColor(200, 60, 200); label = "T"; break;
                case hero::EnemyType::GIANT_MOTH: eColor = QColor(190, 160, 120); label = "M"; break;
                case hero::EnemyType::KEY: eColor = QColor(255, 215, 0); label = "Y"; break;
                case hero::EnemyType::RAFT: eColor = QColor(80, 170, 80); label = "R"; break;
                case hero::EnemyType::POWER_CELL: eColor = QColor(60, 200, 230); label = "E"; break;
                case hero::EnemyType::EXTRA_MINER: eColor = QColor(255, 140, 180); label = "M2"; break;
                default: eColor = QColor(200, 200, 200); label = "?"; break;
            }
            const QRectF er = EntityRect(EntKind::Enemy, i);
            drawSprite(er, EnemyArt(enemy.type), eColor, label);
            if (enemy.type != (int)hero::EnemyType::POWER_CELL
                    && enemy.type != (int)hero::EnemyType::KEY) {
                // the cell and the key have no facing; miners DO (per-slot REFP1)
                const bool spider = enemy.type == (int)hero::EnemyType::SPIDER;
                // a spider/moth next to a wall or the cave edge is forced away
                const int forced = ForcedDirAt(enemy.type, enemy.y, (int)enemy.x);
                DrawFacingArrow(painter, er.toRect(), forced ? forced : enemy.dir,
                                spider);
            }
        }
    } // end level-mode entity rendering
}

void MapCanvas::DrawFacingArrow(QPainter& painter, const QRect& enemyRect, int dir,
                                bool vertical) const {
    // White triangle beside the marker: tip points the way the enemy faces.
    // A spider's "direction" is its first sweep: right = DOWN, left = UP.
    if (vertical) {
        const int cx = enemyRect.center().x();
        const int halfW = std::max(4, enemyRect.width() / 6);
        QPolygonF v;
        if (dir >= 0) {
            const int baseY = enemyRect.bottom() + 2;
            v << QPointF(cx, baseY + 7) << QPointF(cx - halfW, baseY)
              << QPointF(cx + halfW, baseY);
        } else {
            const int baseY = enemyRect.top() - 2;
            v << QPointF(cx, baseY - 7) << QPointF(cx - halfW, baseY)
              << QPointF(cx + halfW, baseY);
        }
        painter.setBrush(QColor(255, 255, 255));
        painter.setPen(QPen(QColor(20, 20, 20), 1));
        painter.drawPolygon(v);
        return;
    }
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

int MapCanvas::CountRoomElementsIn(int roomIdx) const {
    if (!m_levelData || roomIdx < 0 ||
        roomIdx >= (int)m_levelData->rooms.size())
        return 0;
    const hero::RoomData& room = m_levelData->rooms[roomIdx];
    int n = (int)room.enemies.size() + (int)room.lamps.size();
    if (m_levelData->miner_room == roomIdx) n++;
    const hero::ModelData* model =
        GetModelForRoom(const_cast<hero::LevelData*>(m_levelData),
                        const_cast<std::vector<hero::ModelData>*>(m_models),
                        roomIdx);
    if (model) {
        for (int t : model->tiles) {
            if (t == (int)hero::TileType::RAFT || t == (int)hero::TileType::MAGMA_FALL)
                n++;
        }
    }
    return n;
}

int MapCanvas::CountRoomElements() const {
    return CountRoomElementsIn(m_activeRoomIndex);
}

bool MapCanvas::RoomHasCrunch() const {
    // hcrunch is a ROOM feature cell since the 2026-10-17 async move.
    const hero::RoomData* r = AsyncRoomRef();
    if (!r) return false;
    for (const auto& c : r->feature_cells) {
        if (c.size() >= 3 && c[2] == (int)hero::TileType::HCRUNCH)
            return true;
    }
    return false;
}

bool MapCanvas::AllowAddElement(bool asEnemy) {
    if (RoomHasCrunch()) {
        QMessageBox::warning(
            nullptr, QObject::tr("Crunch Room"),
            QObject::tr("A room with a crunch shutter cannot "
                        "contain other objects — the shutter needs the "
                        "sprite slot."));
        return false;
    }
    const hero::ModelData* model =
        GetModelForRoom(const_cast<hero::LevelData*>(m_levelData),
                        const_cast<std::vector<hero::ModelData>*>(m_models),
                        m_activeRoomIndex);
    const hero::RoomData* ar = AsyncRoomRef();
    if (model && ar && (RoomSpecialBits(*ar) & 1)) {
        // Door room (user rule 2026-10-14): a single enemy, nothing else.
        if (!asEnemy) {
            QMessageBox::warning(
                nullptr, QObject::tr("Door Room"),
                QObject::tr("A door room allows a single enemy and "
                            "nothing else — no lamp, miner, raft or "
                            "magma."));
            return false;
        }
        if (CountRoomElements() >= 1) {
            QMessageBox::warning(
                nullptr, QObject::tr("Door Room"),
                QObject::tr("Door rooms allow ONE enemy only."));
            return false;
        }
    }
    if (CountRoomElements() < kMaxRoomElements) return true;
    QMessageBox::warning(
        nullptr, QObject::tr("Element Limit"),
        QObject::tr("Maximum of 2 elements per room (miner, enemies, lamps, raft, magma, ...).\n"
                    "Restricting the number of elements to avoid too much flicker."));
    return false;
}

bool MapCanvas::ElementInRow(int tileY) const {
    if (!m_levelData || m_activeRoomIndex < 0 ||
        m_activeRoomIndex >= (int)m_levelData->rooms.size())
        return false;
    const hero::RoomData& room = m_levelData->rooms[m_activeRoomIndex];
    const int rows = RoomHeightOf(m_levelData, m_models, m_activeRoomIndex) * 4;
    for (const auto& e : room.enemies) {
        if (RowOfY(e.y, rows) == tileY) return true;
    }
    for (const auto& lamp : room.lamps) {
        if (RowOfY(lamp.y, rows) == tileY) return true;
    }
    if (m_levelData->miner_room == m_activeRoomIndex &&
        RowOfY(m_levelData->miner_y, rows) == tileY)
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

void MapCanvas::WarnAsyncBrushNeedsRoomEditor() {
    static bool warned = false;
    if (warned) {
        return;                      // one dialog per session is enough
    }
    warned = true;
    QMessageBox::information(
        nullptr, QObject::tr("Async Walls Are Room-Level Now"),
        QObject::tr(
            "Doors, phase walls and hcrunch bands are ROOM "
            "properties since the 2026-10-17 format change: they live in the "
            "room's async layer (room.asym_patches / room.feature_cells) so "
            "one model shape can be reused by rooms with different async.\n\n"
            "The room-level brush UI for them is the next editor step. "
            "Nothing was changed."));
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
    int displayRows = roomHeight * 4;
    int modelY = tileY / 4;
    int displayColumns = DisplayColumnsFor(roomWidth);

    if (tileX < 0 || tileX >= roomWidth || tileY < 0 || tileY >= displayRows) return;

    int brushVal = static_cast<int>(m_currentBrush);

    // -----------------------------------------------------------------------
    // Async walls (door strip / phase / hcrunch) are ROOM-level since
    // the 2026-10-17 format change: they live in RoomData::asym_patches /
    // feature_cells, never on the model. The brush UI for the room-level layer
    // is the next editor step, so REFUSE here instead of writing the retired
    // model fields — convert hard-fails a model that still carries async.
    // -----------------------------------------------------------------------
    if (m_currentBrush == BrushTool::PHASE_TILE ||
        m_currentBrush == BrushTool::HCRUNCH_TILE ||
        m_currentBrush == BrushTool::DOOR_TILE ||
        m_currentBrush == BrushTool::ASYM_PATCH) {
        if (!room) {
            WarnAsyncBrushNeedsRoomEditor();
            return;
        }
    }

    if (m_currentBrush == BrushTool::SOLID_WALL || m_currentBrush == BrushTool::ERASE_AIR ||
        m_currentBrush == BrushTool::HOT_ROCK_WALL) {
        const int idx = modelY * roomWidth + tileX;
        const int oldTile = model->tiles[idx];
        model->tiles[idx] = brushVal;
        // ERASE_AIR also removes any ROOM async covering this cell (user
        // rule 2026-10-12: empty brush = the ONLY way to remove a patch,
        // same as a sync wall; feature cells go the same way). Snapshot for
        // rollback: opening the cell can SPLIT a wall run into a 5th right
        // rect.
        std::vector<std::vector<int>> removedPatches;
        std::vector<std::vector<int>> removedFeatures;
        hero::RoomData* asyncRoom = room;   // level mode only (guard above)
        if (m_currentBrush == BrushTool::ERASE_AIR && asyncRoom) {
            for (int i = (int)asyncRoom->feature_cells.size() - 1; i >= 0; --i) {
                const auto& c = asyncRoom->feature_cells[i];
                // A P/V/C feature is a ROW property (one kind per row; convert
                // resolves the row and an older paint wrote one cell per
                // column). Matching the stored column left the other cells
                // behind, so the row still drew and "delete did nothing"
                // (user report 2026-10-18). One erase clears the row.
                if (c.size() >= 3 && c[0] == modelY) {
                    removedFeatures.push_back(c);
                    asyncRoom->feature_cells.erase(
                        asyncRoom->feature_cells.begin() + i);
                }
            }
            for (int i = (int)asyncRoom->asym_patches.size() - 1; i >= 0; --i) {
                const auto& p = asyncRoom->asym_patches[i];
                if ((int)p.size() < 3) continue;
                const int pside = (int)p.size() == 4 ? p[3] : 0;
                const int cellCol =
                    pside == 0 ? roomWidth - 1 - p[1] : p[1];
                if (p[0] == modelY && cellCol == tileX) {
                    removedPatches.push_back(p);
                    asyncRoom->asym_patches.erase(
                        asyncRoom->asym_patches.begin() + i);
                }
            }
        }
        int n = 0;
        if (!RightRectsOk(*model, asyncRoom ? *asyncRoom : hero::RoomData(),
                          &n)) {
            model->tiles[idx] = oldTile;
            if (asyncRoom) {
                for (const auto& p : removedPatches)
                    asyncRoom->asym_patches.push_back(p);
                for (const auto& c : removedFeatures)
                    asyncRoom->feature_cells.push_back(c);
            }
            WarnRightRectBudget(n);
            return;
        }
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::PHASE_TILE ||
               m_currentBrush == BrushTool::HCRUNCH_TILE) {
        // Feature grid tiles (convert maps them to chars P/V/C and emits
        // b7 feature records; ERASE_AIR clears them like any tile).
        if (!model || !room) return;      // features are ROOM cells
        // Special features are alone per room (door XOR phase XOR hcrunch)
        // and live ONLY on the middle band (row 1) — top and bottom bands
        // are entry/exit corridors (user rule 2026-10-14).
        {
            const int brushBit =
                (m_currentBrush == BrushTool::PHASE_TILE) ? 2 : 8;
            const int other = RoomSpecialBits(*room) & ~brushBit;
            if (other) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Special Features"),
                    QObject::tr("Special features are alone per room "
                                "(door XOR phase XOR hcrunch). "
                                "Erase the other special feature first."));
                return;
            }
        }
        if (m_currentBrush == BrushTool::HCRUNCH_TILE &&
            CountRoomElements() > 0) {
            QMessageBox::warning(
                nullptr, QObject::tr("Crunch Room"),
                QObject::tr("This room already contains objects (miner, "
                            "enemies, lamps). A crunch shutter cannot share "
                            "the room — remove the objects first."));
            return;
        }
        if (modelY != 1) {
            QMessageBox::warning(
                nullptr, QObject::tr("Special Feature Row"),
                QObject::tr("Special features must sit on row 2 (band 1, "
                            "the middle band) — top/bottom bands are "
                            "entry/exit corridors (convert rejects it "
                            "too)."));
            return;
        }
        int tileVal = (int)hero::TileType::PHASE;
        if (m_currentBrush == BrushTool::HCRUNCH_TILE)
            tileVal = (int)hero::TileType::HCRUNCH;
        // convert allows ONE special kind per room, row 1 only — refuse here
        // instead of writing data that fails the build (user 2026-10-18).
        if (modelY != 1) {
            QMessageBox::warning(
                nullptr, QObject::tr("Special feature"),
                QObject::tr("Phase / hcrunch live on row 1 only."));
            return;
        }
        for (const auto& c : room->feature_cells) {
            if (c.size() >= 3 && c[2] != tileVal) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Special feature"),
                    QObject::tr("This room already carries a different special "
                                "kind — convert allows one per room. Erase the "
                                "existing one first."));
                return;
            }
        }
        // Room feature cell (2026-10-17): the model keeps the shape; the room
        // carries the behaviour. Re-paint = replace the cell's kind.
        std::vector<std::vector<int>> oldFeatures = room->feature_cells;
        for (int i = (int)room->feature_cells.size() - 1; i >= 0; --i) {
            const auto& c = room->feature_cells[i];
            if (c.size() >= 3 && c[0] == modelY)   // row-wide: replace the
                room->feature_cells.erase(          // row's kind in one go
                    room->feature_cells.begin() + i);
        }
        room->feature_cells.push_back({modelY, tileX, tileVal});
        int n = 0;
        if (!RightRectsOk(*model, *room, &n)) {
            room->feature_cells = oldFeatures;
            WarnRightRectBudget(n);
            return;
        }
        emit levelModified();
        update();
    } else if (m_currentBrush == BrushTool::ASYM_PATCH ||
               m_currentBrush == BrushTool::DOOR_TILE) {
        // D6/D6+M1 patch: click the RIGHT half for a ball block (side 0),
        // the LEFT half for an M1 block (side 1). TWO blocks max; the base
        // cell must be OPEN (both objects only add paint/color).
        // DOOR_TILE is the same envelope with tile LOCKED_DOOR (either side;
        // convert hard-fails a model whose patches on one side mix kinds).
        if (!model) return;
        const bool doorBrush = (m_currentBrush == BrushTool::DOOR_TILE);
        const int halfCols = displayColumns / 2;
        if (entityX < 0 || entityX >= displayColumns) return;
        const bool rightHalf = entityX >= halfCols;
        if (doorBrush) {
            // Door lives ONLY on the middle band (row 1), never on the hot
            // band, and is alone per room (user rule 2026-10-14).
            if (modelY != 1) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Async Door"),
                    QObject::tr("The door must sit on row 2 (band 1, the "
                                "middle band) — top/bottom bands are "
                                "entry/exit corridors (convert rejects it "
                                "too)."));
                return;
            }
            if (model->mid_band_type != 0) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Async Door"),
                    QObject::tr("The middle band is HOT — turn the Hot "
                                "selector off (convert rejects it too)."));
                return;
            }
            if (RoomSpecialBits(*room) & ~1) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Special Features"),
                    QObject::tr("Special features are alone per room "
                                "(door XOR phase XOR hcrunch). "
                                "Erase the other special feature first."));
                return;
            }
        }
        const int side = rightHalf ? 0 : 1;
        const int col = rightHalf ? (entityX - halfCols) >> 1 : entityX >> 1;
        if (col < 0 || col >= roomWidth) return;
        const int patchTile = doorBrush ? (int)hero::TileType::LOCKED_DOOR
                                        : (int)hero::TileType::SOLID_WALL;
        const int cellIdx =
            modelY * roomWidth + (rightHalf ? roomWidth - 1 - col : col);
        const int existing = FindPatch(*room, modelY, col, side);
        if (existing < 0) {
            // Two-block cap (convert hard-fails >2 as well).
            if ((int)room->asym_patches.size() >= 2) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Asym Patch"),
                    QObject::tr("Two blocks max per model (stacked on two "
                                "bands, or a pair on one band).\nErase a "
                                "patch first."));
                return;
            }
            if (model->tiles[cellIdx] != (int)hero::TileType::AIR) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Asym Patch"),
                    rightHalf
                        ? QObject::tr("Mirror cell (row %1, col %2) is "
                                      "already a wall — the strip would be "
                                      "invisible in the game.\nPaint where "
                                      "the LEFT half is open.")
                              .arg(modelY + 1)
                              .arg(roomWidth - 1 - col + 1)
                        : QObject::tr("Cell (row %1, col %2) is already a "
                                      "wall — an M1 patch paints wall color "
                                      "over an OPEN cell.\nErase the cell "
                                      "first.")
                              .arg(modelY + 1)
                              .arg(col + 1));
                return;
            }
            // One column per side (single ball-x / M1-x envelope; convert
            // hard-fails mixed columns on the same side) and NO mixed kinds
            // on one side (a door model's async patches must all be door).
            for (const auto& p : room->asym_patches) {
                if ((int)p.size() < 3) continue;
                const int pside = (int)p.size() == 4 ? p[3] : 0;
                if (pside != side) continue;
                if (p[1] != col) {
                    QMessageBox::warning(
                        nullptr, QObject::tr("Asym Patch"),
                        QObject::tr("One strip column per side (single "
                                    "ball/m1 x envelope).\nExisting patches "
                                    "sit at column %1 — erase them first, "
                                    "or paint at column %1.")
                            .arg(p[1] + 1));
                    return;
                }
                if (p[2] != patchTile) {
                    QMessageBox::warning(
                        nullptr,
                        QObject::tr(doorBrush ? "Async Door" : "Asym Patch"),
                        QObject::tr(doorBrush
                            ? "This side already has a plain patch — erase "
                              "it first (a door model's async patches must "
                              "ALL be door tiles)."
                            : "This side already has an async door — erase "
                              "it first (no mixing door and plain patches "
                              "on one side)."));
                    return;
                }
            }
            if (rightHalf) {
                room->asym_patches.push_back({modelY, col, patchTile});
            } else {
                room->asym_patches.push_back({modelY, col, patchTile, 1});
            }
            int n = 0;
            if (!RightRectsOk(*model, *room, &n)) {
                room->asym_patches.pop_back();
                WarnRightRectBudget(n);
                return;
            }
        } else {
            // Patch already here: NO-OP (user rule 2026-10-12 — the async
            // brush only ADDS; re-entry during a drag must not toggle).
            // Removal = the ERASE_AIR brush (same as a sync wall).
            return;
        }
        emit levelModified();
        update();
    // (ADD_RAFT is handled with the other ENTITY brushes below: the raft is a
    // moving object now, not a tile — the static RAFT tile stays valid in
    // hand-authored data as a platform.)
    } else if (m_currentBrush == BrushTool::ADD_MAGMA) {
        int idx = modelY * roomWidth + tileX;
        if (model->tiles[idx] != (int)hero::TileType::MAGMA_FALL && room && !AllowAddElement()) return;
        model->tiles[idx] = (int)hero::TileType::MAGMA_FALL;
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::SET_MINER_GOAL) {
        if (entityX < 0 || entityX >= displayColumns) return;
        if (m_levelData->miner_room == m_activeRoomIndex &&
            (int)std::floor(m_levelData->miner_x * 2.0f) == entityX &&
            RowOfY(m_levelData->miner_y, displayRows) == tileY) {
            m_levelData->miner_dir = m_initialFacing;   // click = set the Facing button's value
            emit levelModified();
            update();
            return;
        }
        if (m_levelData->miner_room != m_activeRoomIndex && !AllowAddElement()) return;
        // Same room: ignore miner's current row (re-place frees it first).
        int ignoreY = (m_levelData->miner_room == m_activeRoomIndex)
                          ? RowOfY(m_levelData->miner_y, displayRows)
                          : -1;
        if (!AllowElementInRow(tileY, ignoreY)) return;
        m_levelData->miner_room = m_activeRoomIndex;
        m_levelData->miner_x = (float)entityX / 2.0f;
        m_levelData->miner_y = YOfRow(tileY, displayRows);
        m_levelData->miner_dir = m_initialFacing;
        emit levelModified();
        update();
    } else if (!m_modelMode && room && (m_currentBrush == BrushTool::ADD_SPIDER || m_currentBrush == BrushTool::ADD_BAT ||
               m_currentBrush == BrushTool::ADD_SNAKE || m_currentBrush == BrushTool::ADD_TENTACLE ||
               m_currentBrush == BrushTool::ADD_RAFT ||
               m_currentBrush == BrushTool::ADD_MOTH || m_currentBrush == BrushTool::ADD_KEY ||
               m_currentBrush == BrushTool::ADD_CELL ||
               m_currentBrush == BrushTool::ADD_MINER2)) {
        // Entity placement: full stage width, no mirroring. Reject rows beyond
        // the cave (tileY >= displayRows) so enemies can't spawn in the HUD.
        if (entityX < 0 || entityX >= displayColumns ||
            tileY < 0 || tileY >= displayRows) return;
        // A spider hangs in a wall-to-wall gap one cell (8 px = 2 display
        // columns) wide: an odd column puts its 8 px sprite half inside the
        // next cell (release 0.8 shot 003). Snap it to the cell's first column
        // (the generator already places spiders on even columns).
        if (m_currentBrush == BrushTool::ADD_SPIDER) entityX &= ~1;
        // An extra miner stands on the floor: wherever he is clicked inside a
        // band, snap him so his 9 visible rows end EXACTLY on the band's last
        // line (top = band edge - 9 px, stage y = 3 * band + 2.25 = 2.25 / 5.25 / 8.25), and
        // a click in the floor band itself uses band 2 (user 2026-10-26: the
        // editor makes the fine adjustment, and he must not sink into the next
        // band). tileY becomes the canvas row that y falls on.
        float snapY = -1.0f;
        if (m_currentBrush == BrushTool::ADD_MINER2) {
            snapY = 3.0f * (float)std::min(tileY / 4, 2) + 2.25f;
            tileY = RowOfY(snapY, displayRows);
        }

        hero::EnemyData eData;
        if (m_currentBrush == BrushTool::ADD_SPIDER) eData.type = (int)hero::EnemyType::SPIDER;
        else if (m_currentBrush == BrushTool::ADD_BAT) eData.type = (int)hero::EnemyType::BAT;
        else if (m_currentBrush == BrushTool::ADD_SNAKE) eData.type = (int)hero::EnemyType::SNAKE;
        else if (m_currentBrush == BrushTool::ADD_TENTACLE) eData.type = (int)hero::EnemyType::TENTACLE;
        else if (m_currentBrush == BrushTool::ADD_RAFT) eData.type = (int)hero::EnemyType::RAFT;
        else if (m_currentBrush == BrushTool::ADD_MOTH) eData.type = (int)hero::EnemyType::GIANT_MOTH;
        else if (m_currentBrush == BrushTool::ADD_CELL) eData.type = (int)hero::EnemyType::POWER_CELL;
        else if (m_currentBrush == BrushTool::ADD_MINER2) eData.type = (int)hero::EnemyType::EXTRA_MINER;
        else eData.type = (int)hero::EnemyType::KEY;

        eData.x = (float)entityX;
        eData.y = snapY >= 0.0f ? snapY : YOfRow(tileY, displayRows);
        // the kernel floats the raft ON the water surface (plank top = line 131)
        if (eData.type == (int)hero::EnemyType::RAFT) eData.y = 131.0f / 12.0f;
        eData.range_min = (float)std::max(0, entityX - 3);
        eData.range_max = (float)std::min(displayColumns - 1, entityX + 3);
        eData.speed = 1.5f;
        eData.dir = m_initialFacing;
        if (ForcedDirAt(eData.type, eData.y, (int)eData.x) != 0)
            eData.dir = ForcedDirAt(eData.type, eData.y, (int)eData.x);   // never first move into a wall/edge

        // Door-room + tentacle rules (user rule 2026-10-14): a door room
        // allows ONE non-key enemy and nothing else; tentacles live in
        // the water on the bottom band, in open cells.
        if (room && (RoomSpecialBits(*room) & 1)) {
            if (m_currentBrush == BrushTool::ADD_KEY || m_currentBrush == BrushTool::ADD_CELL ||
                m_currentBrush == BrushTool::ADD_MINER2) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Door Room"),
                    QObject::tr("No key in a door room — a single enemy "
                                "only."));
                return;
            }
            if ((int)room->enemies.size() >= 1) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Door Room"),
                    QObject::tr("Door rooms allow ONE enemy only."));
                return;
            }
        }
        if (m_currentBrush == BrushTool::ADD_RAFT) {
            // The moving raft floats on OPEN water on the bottom band (user
            // rule: "placed only above water") — the same shape as the
            // tentacle rule, plus the cell must be air (water).
            if (tileY / 4 != 2) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Raft"),
                    QObject::tr("The raft floats on the bottom band "
                                "(rows 9-12)."));
                return;
            }
            if (!room->bottom_band) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Raft"),
                    QObject::tr("Rafts float in water — turn the room's "
                                "bottom band on first."));
                return;
            }
            if (model) {
                const int halfCols = displayColumns / 2;
                const int col = (entityX < halfCols)
                                    ? (entityX >> 1)
                                    : ((displayColumns - 1 - entityX) >> 1);
                if (col >= 0 && col < roomWidth &&
                    model->tiles[2 * roomWidth + col] !=
                        (int)hero::TileType::AIR) {
                    QMessageBox::warning(
                        nullptr, QObject::tr("Raft"),
                        QObject::tr("The raft needs OPEN water — that cell "
                                    "is a wall/ledge. Paint it as air "
                                    "first."));
                    return;
                }
            }
        }
        if (m_currentBrush == BrushTool::ADD_TENTACLE) {
            if (tileY / 4 != 2) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Tentacle"),
                    QObject::tr("Tentacles live on the bottom band "
                                "(rows 9-12)."));
                return;
            }
            if (!room->bottom_band) {
                QMessageBox::warning(
                    nullptr, QObject::tr("Tentacle"),
                    QObject::tr("Tentacles live in water — turn the "
                                "room's bottom band on first."));
                return;
            }
            if (model) {
                const int halfCols = displayColumns / 2;
                const int col = (entityX < halfCols)
                                    ? (entityX >> 1)
                                    : ((displayColumns - 1 - entityX) >> 1);
                if (col >= 0 && col < roomWidth &&
                    model->tiles[2 * roomWidth + col] !=
                        (int)hero::TileType::AIR) {
                    QMessageBox::warning(
                        nullptr, QObject::tr("Tentacle"),
                        QObject::tr("Tentacles need open water — the "
                                    "spawn cell is not empty."));
                    return;
                }
            }
        }

        // Occupied tile: flip existing enemy facing instead of stacking.
        // The key has no facing — warn instead of silently doing nothing.
        for (auto& e : room->enemies) {
            if ((int)std::floor(e.x) == entityX && RowOfY(e.y, displayRows) == tileY) {
                if (m_currentBrush == BrushTool::ADD_KEY || m_currentBrush == BrushTool::ADD_CELL ||
                    m_currentBrush == BrushTool::ADD_MINER2) {
                    QMessageBox::warning(
                        nullptr, QObject::tr("Key"),
                        QObject::tr("An object already sits on this tile — "
                                    "erase it first."));
                    return;
                }
                // a spider's dir is its first sweep (right = down, left = up), a
                // moth's its first leg; next to a wall / the cave edge it is
                // forced away from it and cannot be changed
                if (ForcedDirAt(e.type, e.y, (int)e.x) != 0) {
                    e.dir = ForcedDirAt(e.type, e.y, (int)e.x);
                    update();
                    return;
                }
                e.dir = m_initialFacing;   // click = set the Facing button's value
                emit levelModified();
                update();
                return;
            }
        }

        if (!AllowElementInRow(tileY)) return;
        if (!AllowAddElement(true)) return;
        room->enemies.push_back(eData);
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::ADD_LAMP) {
        // Darkness mask covers rooms 0-7 only — a lamp beyond that could
        // never darken its room (game treats rooms 8+ as always lit).
        if (m_activeRoomIndex >= kDarkMaskRooms) {
            QMessageBox::warning(
                nullptr, QObject::tr("Lamp Limit"),
                QObject::tr("Lamps only work in rooms 0-7 (the darkness mask "
                            "is 8 bits).\nRoom %1 stays permanently lit, so "
                            "no lamp was placed.")
                    .arg(m_activeRoomIndex + 1));
            return;
        }
        // Entity placement: full stage width, no mirroring. No lamps in the HUD band.
        if (entityX < 0 || entityX >= displayColumns ||
            tileY < 0 || tileY >= displayRows) return;

        // Replace any lamp already on this tile, otherwise add a new one
        for (auto& lamp : room->lamps) {
            if ((int)std::floor(lamp.x) == entityX && RowOfY(lamp.y, displayRows) == tileY) {
                lamp.x = (float)entityX + 0.5f;
                lamp.y = YOfRow(tileY, displayRows) + 0.5f * 12.0f / (float)displayRows;
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
        lamp.y = YOfRow(tileY, displayRows) + 0.5f * 12.0f / (float)displayRows;
        lamp.lit = true;
        room->lamps.push_back(lamp);
        emit levelModified();
        update();
    } else if (!m_modelMode && room && m_currentBrush == BrushTool::DELETE_ENTITY) {
        // The Level tab's Delete tool removes the ROOM-side thing at the click:
        // a P/V/C feature ROW (a feature is a row property), the asym patch
        // covering this cell, or a placed entity. Before 2026-10-18 it only
        // removed entities, so Delete anywhere on a hcrunch row did nothing at
        // all — the ERASE_AIR brush was the only way, and only per column
        // (user 2026-10-18: "clicked delete in all columns, still there").
        bool removedRoomLayer = false;
        for (int i = (int)room->feature_cells.size() - 1; i >= 0; --i) {
            const auto& c = room->feature_cells[i];
            if (c.size() >= 3 && c[0] == modelY) {
                room->feature_cells.erase(room->feature_cells.begin() + i);
                removedRoomLayer = true;
            }
        }
        for (int i = (int)room->asym_patches.size() - 1; i >= 0; --i) {
            const auto& p = room->asym_patches[i];
            if ((int)p.size() < 3) continue;
            const int pside = (int)p.size() == 4 ? p[3] : 0;
            const int cellCol = pside == 0 ? roomWidth - 1 - p[1] : p[1];
            if (p[0] == modelY && cellCol == tileX) {
                room->asym_patches.erase(room->asym_patches.begin() + i);
                removedRoomLayer = true;
            }
        }
        if (removedRoomLayer) {
            emit levelModified();
            update();
            return;
        }
        // else fall through: Entities live in full stage coordinates (no
        // mirroring)
        for (auto it = room->enemies.begin(); it != room->enemies.end(); ++it) {
            if ((int)std::floor(it->x) == entityX && RowOfY(it->y, displayRows) == tileY) {
                room->enemies.erase(it);
                emit levelModified();
                update();
                return;
            }
        }
        for (auto it = room->lamps.begin(); it != room->lamps.end(); ++it) {
            if ((int)std::floor(it->x) == entityX && RowOfY(it->y, displayRows) == tileY) {
                room->lamps.erase(it);
                emit levelModified();
                update();
                return;
            }
        }
    }
}

// First-move direction an enemy at (y, col) is forced to, 0 = free: a spider
// (+1 down / -1 up) next to the cave edge or a wall above/below its 24 px
// sweep, a moth (+1 right / -1 left) next to a wall or the screen edge on its
// 8-column patrol. Other types are never forced.
int MapCanvas::ForcedDirAt(int type, float y, int col) const {
    Geo g;
    if (type == (int)hero::EnemyType::SPIDER)
        return GetGeo(g) ? hero::SpiderForcedDirIn(*g.model, y, col)
                         : hero::SpiderForcedDir(y);
    if (type == (int)hero::EnemyType::GIANT_MOTH && GetGeo(g))
        return hero::MothForcedDirIn(*g.model, y, col);
    return 0;
}

bool MapCanvas::GetGeo(Geo& g) const {
    if (m_modelMode || !m_levelData || m_activeRoomIndex < 0 ||
        m_activeRoomIndex >= (int)m_levelData->rooms.size())
        return false;
    g.room = &m_levelData->rooms[m_activeRoomIndex];
    g.model = GetModelForRoom(
        m_levelData, const_cast<std::vector<hero::ModelData>*>(m_models),
        m_activeRoomIndex);
    if (!g.model) return false;
    g.rw = g.model->width;
    g.rh = g.model->height;
    g.cols = DisplayColumnsFor(g.rw);
    g.rows = g.rh * 4;
    g.cellW = m_tileSize;
    g.cellH = CellHeightFor(m_tileSize, g.cols, g.rows);
    g.pxH = (double)g.cellH * g.rows / 144.0;
    return true;
}

// The sprite's 8 px window on the canvas: left edge = its display column,
// top = the scanline the kernel starts drawing at.
QRectF MapCanvas::EntityRect(EntKind kind, int idx) const {
    Geo g;
    if (!GetGeo(g)) return QRectF();
    double col = 0, topPx = 0;
    int rows = 0;
    if (kind == EntKind::Enemy && idx < (int)g.room->enemies.size()) {
        const auto& e = g.room->enemies[idx];
        col = e.x;
        topPx = e.y * 12.0;
        rows = EnemyArt(e.type).n;
    } else if (kind == EntKind::Lamp && idx < (int)g.room->lamps.size()) {
        const auto& l = g.room->lamps[idx];
        col = ((int)(l.x * 4) / 8) * 2;     // art is left-aligned in its cell
        topPx = l.y * 12.0;
        rows = kLampArt.n;
    } else if (kind == EntKind::Miner) {
        col = m_levelData->miner_x * 2.0;
        topPx = m_levelData->miner_y * 12.0 + 3.0;   // kernel draws at MinerY+3
        rows = kMinerArt.n;
    } else {
        return QRectF();
    }
    return QRectF(col * g.cellW, topPx * g.pxH, 2.0 * g.cellW, rows * g.pxH);
}

// convert's _lamp_type: the mirrored design when the wall is on the right only.
bool MapCanvas::LampWallOnRight(int idx) const {
    Geo g;
    if (!GetGeo(g) || idx >= (int)g.room->lamps.size()) return false;
    const auto& l = g.room->lamps[idx];
    const int band = std::clamp(RowOfY(l.y, g.rows) / 4, 0, g.rh - 1);
    const int cell = MirrorColumn(((int)(l.x * 4) / 8) * 2, g.rw);
    auto solid = [&](int c) { return IsWallTile(g.model->tiles[band * g.rw + c]); };
    const bool left = cell > 0 ? solid(cell - 1) : false;
    const bool right = cell < g.rw - 1 ? solid(cell + 1) : false;
    return right && !left;
}

// Can this object stand with its left edge on display column `col` and its
// anchor on canvas row `tileY`? Mirrors convert_level's seat rules: the 8 px
// sprite never overlaps a wall cell (the snake is built to), tentacle/raft sit
// on the bottom water band, miners stand on a solid cell, one object per row.
bool MapCanvas::PlacementOk(EntKind kind, int idx, int type, int col,
                            int tileY) const {
    Geo g;
    if (!GetGeo(g)) return false;
    if (col < 0 || col > g.cols - 2 || tileY < 0 || tileY >= g.rows) return false;
    const int band = tileY / 4;
    auto wallAt = [&](int b, int dcol) {
        if (b < 0 || b >= g.rh) return false;
        return IsWallTile(g.model->tiles[b * g.rw + MirrorColumn(dcol, g.rw)]);
    };
    const bool isSnake = kind == EntKind::Enemy &&
                         type == (int)hero::EnemyType::SNAKE;
    if (!isSnake && (wallAt(band, col) || wallAt(band, col + 1))) return false;

    if (kind == EntKind::Enemy &&
        (type == (int)hero::EnemyType::TENTACLE ||
         type == (int)hero::EnemyType::RAFT) &&
        (band != g.rh - 1 || !g.room->bottom_band))
        return false;
    const bool standing = kind == EntKind::Miner ||
        (kind == EntKind::Enemy && type == (int)hero::EnemyType::EXTRA_MINER);
    if (standing) {
        const int mid = std::min(19, (col * 4 + 3) / 8);
        if (!wallAt(band + 1, mid < 10 ? mid * 2 : (19 - mid) * 2)) return false;
    }
    // one object per canvas row (the editor's flicker rule), ignoring itself
    for (int i = 0; i < (int)g.room->enemies.size(); ++i)
        if (!(kind == EntKind::Enemy && i == idx) &&
            RowOfY(g.room->enemies[i].y, g.rows) == tileY) return false;
    for (int i = 0; i < (int)g.room->lamps.size(); ++i)
        if (!(kind == EntKind::Lamp && i == idx) &&
            RowOfY(g.room->lamps[i].y, g.rows) == tileY) return false;
    if (kind != EntKind::Miner && m_levelData->miner_room == m_activeRoomIndex &&
        RowOfY(m_levelData->miner_y, g.rows) == tileY) return false;
    return true;
}

bool MapCanvas::TryBeginDrag(const QPointF& pos) {
    Geo g;
    if (!GetGeo(g)) return false;
    switch (m_currentBrush) {
        case BrushTool::DELETE_ENTITY: case BrushTool::ERASE_AIR:
        case BrushTool::SOLID_WALL: case BrushTool::HOT_ROCK_WALL:
        case BrushTool::ASYM_PATCH: case BrushTool::DOOR_TILE:
        case BrushTool::PHASE_TILE: case BrushTool::HCRUNCH_TILE:
        case BrushTool::ADD_MAGMA:
            return false;               // those brushes own the click
        default: break;
    }
    EntKind kind = EntKind::None;
    int idx = -1;
    for (int i = (int)g.room->enemies.size() - 1; i >= 0 && idx < 0; --i)
        if (EntityRect(EntKind::Enemy, i).contains(pos)) { kind = EntKind::Enemy; idx = i; }
    for (int i = (int)g.room->lamps.size() - 1; i >= 0 && idx < 0; --i)
        if (EntityRect(EntKind::Lamp, i).contains(pos)) { kind = EntKind::Lamp; idx = i; }
    if (idx < 0 && m_levelData->miner_room == m_activeRoomIndex &&
        EntityRect(EntKind::Miner, 0).contains(pos)) { kind = EntKind::Miner; idx = 0; }
    if (idx < 0) return false;

    const QRectF r = EntityRect(kind, idx);
    const int rowOfEntity = kind == EntKind::Enemy ? RowOfY(g.room->enemies[idx].y, g.rows)
                          : kind == EntKind::Lamp ? RowOfY(g.room->lamps[idx].y, g.rows)
                          : RowOfY(m_levelData->miner_y, g.rows);
    m_dragKind = kind;
    m_dragIdx = idx;
    m_dragGrabCol = (int)(pos.x() / g.cellW) - (int)std::lround(r.x() / g.cellW);
    m_dragGrabRow = (int)(pos.y() / g.cellH) - rowOfEntity;
    m_dragMoved = false;
    m_dragPress = pos;
    return true;
}

void MapCanvas::DragTo(const QPointF& pos) {
    Geo g;
    if (!GetGeo(g) || m_dragKind == EntKind::None) return;
    int type = -1, curCol = 0, curRow = 0;
    if (m_dragKind == EntKind::Enemy) {
        if (m_dragIdx >= (int)g.room->enemies.size()) return;
        const auto& e = g.room->enemies[m_dragIdx];
        type = e.type; curCol = (int)e.x; curRow = RowOfY(e.y, g.rows);
    } else if (m_dragKind == EntKind::Lamp) {
        if (m_dragIdx >= (int)g.room->lamps.size()) return;
        const auto& l = g.room->lamps[m_dragIdx];
        curCol = ((int)(l.x * 4) / 8) * 2; curRow = RowOfY(l.y, g.rows);
    } else {
        curCol = (int)std::lround(m_levelData->miner_x * 2.0);
        curRow = RowOfY(m_levelData->miner_y, g.rows);
    }
    int col = (int)(pos.x() / g.cellW) - m_dragGrabCol;
    int row = (int)(pos.y() / g.cellH) - m_dragGrabRow;
    if (m_dragKind == EntKind::Miner) row = curRow;     // Y is a ROM constant
    row = std::clamp(row, 0, g.rows - 1);
    const bool whole = m_dragKind == EntKind::Lamp ||
                       (m_dragKind == EntKind::Enemy &&
                        type == (int)hero::EnemyType::SPIDER);   // whole cells
    const bool seated = type == (int)hero::EnemyType::EXTRA_MINER;
    if (seated)      // feet on the band's last line, like the placement brush
        row = RowOfY(3.0f * (float)std::min(row / 4, 2) + 2.25f, g.rows);
    if (whole) col &= ~1;

    // nearest legal column on that row (a few steps either way), else stay
    const int step = whole ? 2 : 1;
    for (int k = 0; k <= 3; ++k) {
        for (int sgn = (k == 0 ? 1 : -1); sgn <= 1; sgn += 2) {
            const int c = col + sgn * k * step;
            if (!PlacementOk(m_dragKind, m_dragIdx, type, c, row)) continue;
            if (c == curCol && row == curRow) return;
            m_dragMoved = true;
            if (m_dragKind == EntKind::Enemy) {
                auto& e = g.room->enemies[m_dragIdx];
                const float d = (float)(c - (int)e.x);
                e.x = (float)c;
                e.y = seated ? 3.0f * (float)std::min(row / 4, 2) + 2.25f
                    : type == (int)hero::EnemyType::RAFT ? 131.0f / 12.0f
                    : YOfRow(row, g.rows);
                if (ForcedDirAt(type, e.y, (int)e.x) != 0)
                    e.dir = ForcedDirAt(type, e.y, (int)e.x);
                e.range_min = std::max(0.0f, e.range_min + d);
                e.range_max = std::min((float)g.cols - 1, e.range_max + d);
            } else if (m_dragKind == EntKind::Lamp) {
                auto& l = g.room->lamps[m_dragIdx];
                l.x = (float)c + 0.5f;
                l.y = YOfRow(row, g.rows) + 0.5f * 12.0f / (float)g.rows;
            } else {
                m_levelData->miner_x = (float)c / 2.0f;
            }
            emit levelModified();
            update();
            return;
        }
    }
}

void MapCanvas::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::LeftButton) {
        if (TryBeginDrag(event->position())) return;   // click applies on release
        MouseToTile(event->position(), /*apply=*/true);
    }
}

void MapCanvas::mouseMoveEvent(QMouseEvent* event) {
    if (m_dragKind != EntKind::None) {
        MouseToTile(event->position(), /*apply=*/false);
        if (event->buttons() & Qt::LeftButton) DragTo(event->position());
        return;
    }
    MouseToTile(event->position(), event->buttons() & Qt::LeftButton);
}

void MapCanvas::mouseReleaseEvent(QMouseEvent* event) {
    if (m_dragKind != EntKind::None) {
        const bool moved = m_dragMoved;
        const EntKind kind = m_dragKind;
        const int idx = m_dragIdx;
        m_dragKind = EntKind::None;
        m_dragIdx = -1;
        if (moved) return;
        // A plain click on an object whose brush is selected sets its facing to
        // the Facing button's value, wherever on the sprite it was hit (user
        // 2026-10-28: pick the element's brush, set Facing, click the element).
        Geo g;
        if (GetGeo(g)) {
            if (kind == EntKind::Miner && m_currentBrush == BrushTool::SET_MINER_GOAL) {
                m_levelData->miner_dir = m_initialFacing;
                emit levelModified();
                update();
                return;
            }
            if (kind == EntKind::Enemy && idx < (int)g.room->enemies.size()) {
                auto& e = g.room->enemies[idx];
                const bool sameBrush =
                    (m_currentBrush == BrushTool::ADD_SPIDER && e.type == (int)hero::EnemyType::SPIDER) ||
                    (m_currentBrush == BrushTool::ADD_BAT && e.type == (int)hero::EnemyType::BAT) ||
                    (m_currentBrush == BrushTool::ADD_SNAKE && e.type == (int)hero::EnemyType::SNAKE) ||
                    (m_currentBrush == BrushTool::ADD_TENTACLE && e.type == (int)hero::EnemyType::TENTACLE) ||
                    (m_currentBrush == BrushTool::ADD_MOTH && e.type == (int)hero::EnemyType::GIANT_MOTH) ||
                    (m_currentBrush == BrushTool::ADD_MINER2 && e.type == (int)hero::EnemyType::EXTRA_MINER);
                if (sameBrush) {
                    const int forced = ForcedDirAt(e.type, e.y, (int)e.x);
                    e.dir = forced ? forced : m_initialFacing;
                    emit levelModified();
                    update();
                    return;
                }
            }
        }
        MouseToTile(m_dragPress, /*apply=*/true);   // otherwise: the brush as before
        return;
    }
    // Live feature checks fire on RELEASE only — never mid-drag (a drag
    // legitimately passes through invalid layouts cell by cell).
    if (m_modelMode &&
        (m_currentBrush == BrushTool::PHASE_TILE ||
         m_currentBrush == BrushTool::HCRUNCH_TILE)) {
        ValidateFeatureTiles();
    }
    QWidget::mouseReleaseEvent(event);
}

void MapCanvas::ValidateFeatureTiles() {
    if (!m_models || m_activeModelIndex < 0 ||
        m_activeModelIndex >= (int)m_models->size())
        return;
    const hero::ModelData& model = (*m_models)[m_activeModelIndex];
    const hero::RoomData* ar = AsyncRoomRef();
    if (!ar) return;          // async is a room property: nothing to validate
    QStringList problems;

    // Special features are alone per room (convert: hard error)
    {
        const int bits = RoomSpecialBits(*ar);
        QStringList kinds;
        if (bits & 1) kinds << "door";
        if (bits & 2) kinds << "phase";
        if (bits & 8) kinds << "hcrunch";
        if (kinds.size() > 1)
            problems << tr("Mixed special features %1 — specials are alone "
                           "per room (door XOR phase XOR hcrunch); "
                           "convert will fail.")
                        .arg(kinds.join(", "));
    }

    // phase on the hot middle band (convert: hard error). hcrunch IS
    // allowed on hot (user rule 2026-10-14: the crunch band respects the
    // hot flag — convert flags it in MetaB b6).
    if (model.mid_band_type != 0) {
        QStringList hits;
        for (const auto& c : ar->feature_cells) {
            if (c.size() >= 3 && c[1] < model.width &&
                c[2] == (int)hero::TileType::PHASE)
                hits << QString::number(c[1] + 1);
        }
        if (!hits.isEmpty())
            problems << tr("Phase on the HOT middle band at col(s) %1 "
                           "— hot and blinking are mutually exclusive "
                           "(convert will fail).\nTurn the "
                           "middle-band Hot selector off.")
                        .arg(hits.join(", "));
    }

    // Special features off the middle band (row 1) — convert: hard error.
    // Top/bottom bands are entry/exit corridors (user rule 2026-10-14).
    {
        QStringList hits;
        for (int r = 0; r < model.height; ++r) {
            if (r == 1) continue;
            for (int c = 0; c < model.width && c < 10; ++c) {
                int t = model.tiles[r * model.width + c];
                if (t == (int)hero::TileType::PHASE ||
                    t == (int)hero::TileType::HCRUNCH)
                    hits << QString("%1,%2").arg(r + 1).arg(c + 1);
            }
        }
        if (!hits.isEmpty())
            problems << tr("Special feature off the middle band at "
                           "cell(s) %1 — specials sit on row 2 (band 1); "
                           "convert rejects it too.")
                        .arg(hits.join(", "));
    }

    // hcrunch purity: ALL cells in ONE band + contiguous prefix from col 0
    std::array<bool, 8> bandUsed{};   // one per model row (N=4 now)
    bool colUsed[10] = {false};
    int maxCol = -1;
    for (int r = 0; r < model.height; ++r) {
        for (int c = 0; c < model.width && c < 10; ++c) {
            if (model.tiles[r * model.width + c] ==
                (int)hero::TileType::HCRUNCH) {
                bandUsed[r] = true;
                colUsed[c] = true;
                if (c > maxCol) maxCol = c;
            }
        }
    }
    if (maxCol >= 0) {
        QStringList bands, cols;
        int bandCount = 0;
        bool prefixOk = true;
        for (int r = 0; r < (int)bandUsed.size(); ++r)
            if (bandUsed[r]) { ++bandCount; bands << QString::number(r + 1); }
        for (int c = 0; c <= maxCol; ++c)
            if (!colUsed[c]) prefixOk = false;
        for (int c = 0; c < 10; ++c)
            if (colUsed[c]) cols << QString::number(c + 1);
        if (bandCount != 1 || !bandUsed[1] || !prefixOk)
            problems << tr("Horizontal crunch cells must all sit in the "
                           "middle band (row 2) and form a contiguous "
                           "prefix from the left edge (cols 1..n).\n"
                           "Found band(s) %1, col(s) %2 — "
                           "convert will fail.")
                         .arg(bands.join(", "), cols.join(", "));
    }

    if (!problems.isEmpty())
        QMessageBox::warning(nullptr, tr("Feature Check"),
                             problems.join("\n\n"));
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

    int cellH = CellHeightFor(m_tileSize, DisplayColumnsFor(roomWidth), roomHeight * 4);
    int displayCol = (int)(pos.x() / m_tileSize);
    int tileX = MirrorColumn(displayCol, roomWidth);
    int tileY = (int)(pos.y() / cellH);
    emit mouseMovedToTile(tileX, tileY);
    if (apply)
        // tileX is the mirrored model cell for tiles; displayCol is the raw
        // full-stage column (0..4*width-1) used by ApplyBrushAt for entities
        // and the asym-patch brush.
        ApplyBrushAt(tileX, displayCol, tileY);
}

void MapCanvas::SetActiveModel(int modelIndex) {
    m_activeModelIndex = modelIndex;
    update();
}

} // namespace editor
