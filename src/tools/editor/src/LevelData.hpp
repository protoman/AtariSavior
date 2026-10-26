/*
 * Savior AI - Atari 2600
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

#include <string>
#include <vector>
#include <cstdint>
#include <cereal/archives/json.hpp>
#include <cereal/types/vector.hpp>
#include <cereal/types/string.hpp>

namespace hero {

// Room grid (D7 2026-10-20, N=4 2026-10-24): 10 cells per half (8 px each =
// 20 display columns per half, 40 total), 4 bands tall (each band = 36
// scanlines, 4 display rows). One model row == one drawn colour band.
//
// THE PLAYFIELD IS LEFT-RIGHT MIRRORED (CTRLPF reflection), so the half is
// drawn TWICE: cell 0 is the screen's OUTER edge on BOTH sides (display columns
// 0-7 and 152-159) and cell 9 is the CENTER seam (columns 72-87). That is why
// a horizontal exit is ONE cell (col 0, row 1) and is inherently two-sided:
// carving it opens the west and the east edge of the room at once, and
// collision mirrors too (PlayerHitsMap maps display col >= 20 to 39-col).
//
// Exit spans — ONE definition, shared by the editor's "Add Room" carving and
// DataSerializer::Build20LevelStage (E2). The vertical span used to read 8..11
// from the retired 20-cell grid, which wrote into the NEXT row's cells 0/1.
constexpr int kRoomWidth = 10;
constexpr int kRoomHeight = 4;   // N=4: one row per drawn band (36 lines)
constexpr int kVertExitA = 8;    // top/bottom opening: cells 8..9 (centre)
constexpr int kVertExitB = 9;
constexpr int kHorizExitA = 1;   // left/right opening: the WALKABLE bands,
constexpr int kHorizExitB = 2;   //   i.e. rows 1..height-2 (a 4-band room opens
                                 //   bands 1 AND 2 so a side exit can be taken
                                 //   from either; a legacy 3-row model opens
                                 //   band 1 only — its row 2 is the floor)
constexpr int kHorizExitCol = 0; // the mirrored OUTER edge, not the seam (9)

enum class TileType : int {
    AIR = 0,
    SOLID_WALL = 1,      // Indestructible wall
    FRAGILE_WALL = 2,    // Destroyed by Laser or Dynamite
    REINFORCED_WALL = 3, // Destroyed ONLY by Dynamite
    LAVA = 4,            // Instant death
    WATER = 5,           // Instant death/drown
    RAFT = 6,            // Floating raft on water/lava
    MAGMA_FALL = 7,      // Periodic dropping hazard
    HOT_ROCK_WALL = 8,   // Solid wall; pulses yellow/red, kills on touch
    LOCKED_DOOR = 9,     // async side-0 PATCH tile only (never grid — convert
                         // rejects it in tiles[]; MetaB b7 in ROM)
    PHASE = 10,          // grid: blinking wall (PF bit swap + rect w toggle)
    HCRUNCH = 12         // grid: horizontal crunch band (prefix cols 0..n)
};

enum class EnemyType : int {
    SPIDER = 0,
    BAT = 1,
    SNAKE = 2,
    TENTACLE = 3,
    GIANT_MOTH = 4,
    // 5 = LAMP in the ROM merged table (lamps live in RoomData.lamps, never
    // as an editor enemy type) — keep 5 unused here to match convert.
    KEY = 6,             // collectible key (HUD icon; sets KeyHeld)
    // 7 = the moving/rideable raft (2026-10-18): floats on OPEN water on the
    // bottom band, carries the player across and returns. Convert enforces
    // water + row 2 + an open cell (plans/raft_moving_plan.md). The RAFT
    // *tile* (6) stays supported as a static platform for hand-authored data.
    RAFT = 7,
    // 14 = the POWER CELL (2026-10-26): KEY|8 in the ROM (every `and #7` type
    // consumer folds it to the key arm, which tells them apart by the record).
    // Collected once per level, it refills the timer bar. Convert accepts it as a
    // plain pickup: not in door/hcrunch rooms, rooms distinct mod 4 per level.
    POWER_CELL = 14,
    // 15 = an EXTRA MINER (2026-10-26): rescued like the level's own miner; the
    // level ends once every miner is taken. At most two per level, in rooms of
    // different parity, standing on the floor band (canvas row 11, y = 8.25).
    EXTRA_MINER = 15
};

struct EnemyData {
    int type = 0; // 0: SPIDER, 1: BAT, 2: SNAKE, 3: TENTACLE, 4: GIANT_MOTH,
                  // 6: KEY, 7: RAFT (moving, over water)
    float x = 0.0f;
    float y = 0.0f;
    float range_min = 0.0f;
    float range_max = 0.0f;
    float speed = 1.0f;
    int dir = 1;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(type),
           CEREAL_NVP(x),
           CEREAL_NVP(y),
           CEREAL_NVP(range_min),
           CEREAL_NVP(range_max),
           CEREAL_NVP(speed),
           CEREAL_NVP(dir));
    }
};

struct LampData {
    float x = 0.0f;
    float y = 0.0f;
    bool lit = true; // Touching/shooting it turns the room dark

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(x),
           CEREAL_NVP(y),
           CEREAL_NVP(lit));
    }
};

struct ModelData {
    int id = 0;
    std::string name = "Model";
    int width = 20;
    int height = kRoomHeight;   // 4 rows = 4 bands (legacy 3-row files are
                                // migrated on load: see
                                // DataSerializer::MigrateToFourBands)
    std::vector<int> tiles;
    // LEGACY (pre-2026-10-17): async walls used to live here; they are now
    // per-ROOM (RoomData::asym_patches / feature_cells). Kept so an older
    // project still LOADS — DataSerializer::MigrateAsyncToRooms() then moves
    // them into every room that references the model and clears this field,
    // so a save always writes the room-level form.
    std::vector<std::vector<int>> asym_patches;
    // Middle band (row 1) type: 0 = Rock Solid, 1 = Hot. Optional in the
    // file (absent = 0 = solid — pre-mid_band_type files stay key-less).
    // Convert makes EVERY non-air row-1 cell hot when 1; rows 0/2 never
    // get hot (a legacy HOT_ROCK tile there coerces to a normal wall).
    int mid_band_type = 0;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(id),
           CEREAL_NVP(name),
           CEREAL_NVP(width),
           CEREAL_NVP(height),
           CEREAL_NVP(tiles));
        if (Archive::is_loading::value) {
            try {
                ar(CEREAL_NVP(asym_patches));
            } catch (const cereal::Exception&) {
                asym_patches.clear();   // no key in an older file
            }
            try {
                ar(CEREAL_NVP(mid_band_type));
            } catch (const cereal::Exception&) {
                mid_band_type = 0;      // no key in an older file
            }
        } else {
            if (!asym_patches.empty()) {
                ar(CEREAL_NVP(asym_patches));
            }
            if (mid_band_type != 0) {
                ar(CEREAL_NVP(mid_band_type));
            }
        }
    }
};

struct RoomData {
    int room_id = 0;
    int model_id = 0;
    int room_x = 0;
    int room_y = 0;
    std::vector<EnemyData> enemies;
    std::vector<LampData> lamps;
    // Bottom band: optional colored strip on model row 2 (scanlines 96-143).
    // bottom_band=false or color byte 0 in ROM = off.
    bool bottom_band = false;
    int bottom_r = 0;
    int bottom_g = 0;
    int bottom_b = 0;
    // Async walls live on the ROOM (2026-10-17 format change) so one model
    // SHAPE can be reused by rooms with different async. Same encoding the
    // model used to carry:
    //   asym_patches : [row, col, tile] (right/ball) or [row, col, tile, side]
    //                  (side 0 = right/ball, 1 = left/M1); col is the half's
    //                  own cell index; TWO entries max (one x per side).
    //   feature_cells: [row, col, tile] with tile 10/12 (PHASE/HCRUNCH),
    //                  row 1 only, one kind per room.
    // Optional in the file: absent/empty = no async, so a room without async
    // stays key-less (byte-identical to the pre-2026-10-17 emission).
    std::vector<std::vector<int>> asym_patches;
    std::vector<std::vector<int>> feature_cells;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(room_id),
           CEREAL_NVP(model_id),
           CEREAL_NVP(room_x),
           CEREAL_NVP(room_y),
           CEREAL_NVP(enemies),
           CEREAL_NVP(lamps),
           CEREAL_NVP(bottom_band),
           CEREAL_NVP(bottom_r),
           CEREAL_NVP(bottom_g),
           CEREAL_NVP(bottom_b));
        if (Archive::is_loading::value) {
            try {
                ar(CEREAL_NVP(asym_patches));
            } catch (const cereal::Exception&) {
                asym_patches.clear();       // no key in an older/newer file
            }
            try {
                ar(CEREAL_NVP(feature_cells));
            } catch (const cereal::Exception&) {
                feature_cells.clear();
            }
        } else {
            if (!asym_patches.empty()) {
                ar(CEREAL_NVP(asym_patches));
            }
            if (!feature_cells.empty()) {
                ar(CEREAL_NVP(feature_cells));
            }
        }
    }
};

struct LevelData {
    int level_id = 1;
    std::string name = "Level 1";
    // Two wall colors: model rows 0 and 2 use wall_r/g/b; row 1 uses wall2.
    int wall_r = 56;
    int wall_g = 104;
    int wall_b = 144;
    int wall2_r = 40;
    int wall2_g = 130;
    int wall2_b = 90;
    
    int start_room = 0;

    int miner_room = 0;
    float miner_x = 8.0f;
    float miner_y = 9.0f;
    int miner_dir = -1; // -1 = left, +1 = right; existing miner sprite faces left

    std::vector<RoomData> rooms;

    template <class Archive>
    void serialize(Archive& ar, std::uint32_t version) {
        ar(CEREAL_NVP(level_id),
           CEREAL_NVP(name),
           CEREAL_NVP(wall_r),
           CEREAL_NVP(wall_g),
           CEREAL_NVP(wall_b),
           CEREAL_NVP(wall2_r),
           CEREAL_NVP(wall2_g),
           CEREAL_NVP(wall2_b),
           CEREAL_NVP(start_room),
           CEREAL_NVP(miner_room),
           CEREAL_NVP(miner_x),
           CEREAL_NVP(miner_y));
        if (version >= 1) ar(CEREAL_NVP(miner_dir));
        else miner_dir = -1;
        ar(CEREAL_NVP(rooms));
    }
};

// Global models container (stored separately in models/models.json)
struct ModelsFile {
    std::vector<ModelData> models;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(models));
    }
};

// Unified stage file (E1 2026-10-20): models + every level in ONE json.
// Canonical on-disk form is `{"stage": {"models": [...], "levels": [...]}}`;
// each entry of `levels` is exactly a legacy level_00N.json's `level` payload
// (so the converter and the editor see the same objects). The bare
// `{"models": ..., "levels": ...}` form is accepted on load.
struct StageFile {
    std::vector<ModelData> models;
    std::vector<LevelData> levels;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(models), CEREAL_NVP(levels));
    }
};

} // namespace hero

CEREAL_CLASS_VERSION(hero::LevelData, 1)
