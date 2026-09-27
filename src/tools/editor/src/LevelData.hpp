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

enum class TileType : int {
    AIR = 0,
    SOLID_WALL = 1,      // Indestructible wall
    FRAGILE_WALL = 2,    // Destroyed by Laser or Dynamite
    REINFORCED_WALL = 3, // Destroyed ONLY by Dynamite
    LAVA = 4,            // Instant death
    WATER = 5,           // Instant death/drown
    RAFT = 6,            // Floating raft on water/lava
    MAGMA_FALL = 7,      // Periodic dropping hazard
    HOT_ROCK_WALL = 8    // Solid wall; pulses yellow/red, kills on touch
};

enum class EnemyType : int {
    SPIDER = 0,
    BAT = 1,
    SNAKE = 2,
    TENTACLE = 3,
    GIANT_MOTH = 4
};

struct EnemyData {
    int type = 0; // 0: SPIDER, 1: BAT, 2: SNAKE, 3: TENTACLE, 4: GIANT_MOTH
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
    int height = 3;
    std::vector<int> tiles;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(id),
           CEREAL_NVP(name),
           CEREAL_NVP(width),
           CEREAL_NVP(height),
           CEREAL_NVP(tiles));
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

} // namespace hero

CEREAL_CLASS_VERSION(hero::LevelData, 1)
