/*
 * Savior SDL - H.E.R.O. Atari 2600 Remake
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
    MAGMA_FALL = 7       // Periodic dropping hazard
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

struct RoomData {
    int room_id = 0;
    int room_x = 0;
    int room_y = 0;
    int width = 20;      // Savannah Atari prototype: 20 tiles wide (mirrored to a 40-col screen)
    int height = 16;     //                                   16 tiles tall
    std::vector<int> tiles;
    std::vector<EnemyData> enemies;
    std::vector<LampData> lamps;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(room_id),
           CEREAL_NVP(room_x),
           CEREAL_NVP(room_y),
           CEREAL_NVP(width),
           CEREAL_NVP(height),
           CEREAL_NVP(tiles),
           CEREAL_NVP(enemies),
           CEREAL_NVP(lamps));
    }
};

struct LevelData {
    int level_id = 1;
    std::string name = "Level 1";
    int wall_r = 56;
    int wall_g = 104;
    int wall_b = 144;
    
    int start_room = 0;
    float start_x = 8.0f;
    float start_y = 2.0f;

    int miner_room = 0;
    float miner_x = 8.0f;
    float miner_y = 9.0f;

    std::vector<RoomData> rooms;

    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(level_id),
           CEREAL_NVP(name),
           CEREAL_NVP(wall_r),
           CEREAL_NVP(wall_g),
           CEREAL_NVP(wall_b),
           CEREAL_NVP(start_room),
           CEREAL_NVP(start_x),
           CEREAL_NVP(start_y),
           CEREAL_NVP(miner_room),
           CEREAL_NVP(miner_x),
           CEREAL_NVP(miner_y),
           CEREAL_NVP(rooms));
    }
};

} // namespace hero
