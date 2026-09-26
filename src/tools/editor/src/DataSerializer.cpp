/*
 * Savior AI - Atari 2600 (de)Remake of HERO
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

#include "DataSerializer.hpp"
#include <fstream>
#include <iostream>
#include <filesystem>
#include <map>
#include <sstream>
#include <iterator>

namespace hero {

bool DataSerializer::SaveLevelToFile(const LevelData& level, const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        archive(cereal::make_nvp("level", level));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save level to " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::LoadLevelFromFile(LevelData& level, const std::string& filepath) {
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        std::string json((std::istreambuf_iterator<char>(is)), std::istreambuf_iterator<char>());
        if (json.find("\"cereal_class_version\"") == std::string::npos) {
            const size_t levelName = json.find("\"level\"");
            const size_t objectStart = levelName == std::string::npos
                                           ? std::string::npos
                                           : json.find('{', levelName);
            if (objectStart != std::string::npos) {
                const auto version = json.find("\"miner_dir\"") == std::string::npos ? 0 : 1;
                json.insert(objectStart + 1,
                            "\n        \"cereal_class_version\": " +
                                std::to_string(version) + ",");
            }
        }
        std::istringstream input(json);
        cereal::JSONInputArchive archive(input);
        archive(cereal::make_nvp("level", level));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load level from " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::SaveModelsToFile(const std::vector<ModelData>& models, const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        ModelsFile mf;
        mf.models = models;
        archive(cereal::make_nvp("models_file", mf));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save models to " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

bool DataSerializer::LoadModelsFromFile(std::vector<ModelData>& models, const std::string& filepath) {
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        cereal::JSONInputArchive archive(is);
        ModelsFile mf;
        archive(cereal::make_nvp("models_file", mf));
        models = mf.models;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load models from " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

// Atari 2600-inspired cave palettes per level (RGB), shared by generators
static const int kLevelPalettes[20][3] = {
    {180, 80, 0},    // L1: Red/Orange
    {0, 140, 180},   // L2: Cyan/Blue
    {40, 160, 40},   // L3: Green
    {180, 140, 0},   // L4: Yellow/Gold
    {160, 40, 160},  // L5: Purple
    {180, 60, 60},   // L6: Crimson
    {40, 180, 160},  // L7: Teal
    {140, 100, 40},  // L8: Ochre
    {60, 60, 180},   // L9: Deep Blue
    {180, 100, 140}, // L10: Pink/Rose
    {100, 140, 60},  // L11: Lime Green
    {200, 120, 40},  // L12: Amber
    {80, 160, 200},  // L13: Sky Blue
    {160, 80, 160},  // L14: Violet
    {180, 180, 60},  // L15: Olive
    {200, 60, 100},  // L16: Magenta
    {60, 180, 80},   // L17: Emerald
    {140, 80, 200},  // L18: Purple Blue
    {200, 140, 80},  // L19: Copper
    {220, 220, 220}  // L20: Silver Gray
};

static ModelData CreateDefaultModel(int modelId) {
    ModelData model;
    model.id = modelId;
    model.name = "Model " + std::to_string(modelId + 1);
    model.width = 20;
    model.height = 3;
    model.tiles.resize(20 * 3, (int)TileType::AIR);

    // Standard border walls
    for (int x = 0; x < 20; ++x) {
        model.tiles[0 * 20 + x] = (int)TileType::SOLID_WALL;
        model.tiles[2 * 20 + x] = (int)TileType::SOLID_WALL;
    }
    for (int y = 0; y < 3; ++y) {
        model.tiles[y * 20 + 0] = (int)TileType::SOLID_WALL;
        model.tiles[y * 20 + 19] = (int)TileType::SOLID_WALL;
    }
    return model;
}

static RoomData CreateRoomWithModel(int roomId, int modelId, int roomX, int roomY) {
    RoomData room;
    room.room_id = roomId;
    room.model_id = modelId;
    room.room_x = roomX;
    room.room_y = roomY;
    return room;
}

void DataSerializer::GenerateAll20DefaultLevels(const std::string& outputDirectory) {
    std::filesystem::create_directories(outputDirectory);

    // Collect all models across all levels into a global models vector
    std::vector<ModelData> allModels;
    int nextModelId = 0;

    for (int l = 1; l <= 20; ++l) {
        LevelData lvl;
        lvl.level_id = l;
        lvl.name = "Level " + std::to_string(l);
        lvl.wall_r = kLevelPalettes[l - 1][0];
        lvl.wall_g = kLevelPalettes[l - 1][1];
        lvl.wall_b = kLevelPalettes[l - 1][2];

        lvl.start_room = 0;

        int numRooms = 2 + (l / 2);
        if (numRooms > 8) numRooms = 8;

        lvl.miner_room = numRooms - 1;
        lvl.miner_x = 13.0f;
        lvl.miner_y = 10.0f;

        for (int r = 0; r < numRooms; ++r) {
            // Each room gets its own model
            ModelData model = CreateDefaultModel(nextModelId);
            model.name = "Level " + std::to_string(l) + " Room " + std::to_string(r + 1);

            // Open shaft connection between vertical rooms
            if (r < numRooms - 1) {
                for (int x = 8; x <= 11; ++x) {
                    model.tiles[2 * 20 + x] = (int)TileType::AIR;
                }
            }
            if (r > 0) {
                for (int x = 8; x <= 11; ++x) {
                    model.tiles[0 * 20 + x] = (int)TileType::AIR;
                }
            }

            if (r == 0) {
                for (int x = 8; x <= 11; ++x) {
                    model.tiles[2 * 20 + x] = (int)TileType::AIR;
                }
            } else if (r == numRooms - 1) {
                for (int x = 8; x <= 11; ++x) {
                    model.tiles[2 * 20 + x] = (int)TileType::AIR;
                }
            } else {
                model.tiles[1 * 20 + 4] = (int)TileType::SOLID_WALL;
                model.tiles[1 * 20 + 12] = (int)TileType::SOLID_WALL;
            }

            allModels.push_back(model);

            // Create room referencing this model
            RoomData room = CreateRoomWithModel(r, nextModelId, 0, r);
            nextModelId++;

            // Entity placement
            if (r == 0) {
                EnemyData spider;
                spider.type = (int)EnemyType::SPIDER;
                spider.x = 10.0f;
                spider.y = 3.0f;
                spider.range_min = 2.0f;
                spider.range_max = 8.0f;
                spider.speed = 1.0f + (l * 0.1f);
                spider.dir = 1;
                room.enemies.push_back(spider);
            } else if (r == numRooms - 1) {
                EnemyData snake;
                snake.type = (int)EnemyType::SNAKE;
                snake.x = 8.0f;
                snake.y = 10.0f;
                snake.range_min = 6.0f;
                snake.range_max = 12.0f;
                snake.speed = 1.2f + (l * 0.1f);
                snake.dir = 1;
                room.enemies.push_back(snake);
            } else {
                if (r % 2 == 1) {
                    EnemyData bat;
                    bat.type = (int)EnemyType::BAT;
                    bat.x = 4.0f;
                    bat.y = 4.0f;
                    bat.range_min = 2.0f;
                    bat.range_max = 13.0f;
                    bat.speed = 1.5f + (l * 0.15f);
                    bat.dir = 1;
                    room.enemies.push_back(bat);
                }
                if (l >= 2 && r % 2 == 0) {
                    LampData lamp;
                    lamp.x = 3.5f;
                    lamp.y = 10.5f;
                    room.lamps.push_back(lamp);
                }
            }

            lvl.rooms.push_back(room);
        }

        std::string filename = outputDirectory + "/level_" + (l < 10 ? "0" : "") + std::to_string(l) + ".json";
        SaveLevelToFile(lvl, filename);
    }

    // Save all models to models/models.json
    std::string modelsDir = outputDirectory + "/models";
    std::filesystem::create_directories(modelsDir);
    SaveModelsToFile(allModels, modelsDir + "/models.json");
}

// ---------------------------------------------------------------------------
// Authentic stage import: converts pixel-decoded maps of the original
// Activision H.E.R.O. levels (source: atariage.com HEROMaps by Adam Lewis)
// into standard LevelData JSON files.
// ---------------------------------------------------------------------------
namespace {

struct AuthEntity {
    int col = 0;
    int row = 0;
    int n = 0;
    std::string kind;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(col), CEREAL_NVP(row), CEREAL_NVP(n), CEREAL_NVP(kind));
    }
};

struct AuthRoom {
    std::vector<std::string> grid;
    std::vector<AuthEntity> entities;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(grid), CEREAL_NVP(entities));
    }
};

struct AuthLevel {
    int id = 0;
    std::vector<AuthRoom> rooms;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(id), CEREAL_NVP(rooms));
    }
};

struct AuthFile {
    std::vector<AuthLevel> levels;
    template <class Archive>
    void serialize(Archive& ar) {
        ar(CEREAL_NVP(levels));
    }
};

// Maps a 16-wide engine column onto the 19-wide source map column
static int SrcCol(int c) {
    int s = (int)(((c + 0.5f) * 19.0f / 16.0f) - 0.5f);
    return std::max(0, std::min(18, s));
}

static bool Passable(char ch) { return ch != '#' && ch != 'M' && ch != 'F'; }

} // namespace

bool DataSerializer::ImportAuthenticMaps(const std::string& intermediateJsonPath, const std::string& outputDirectory) {
    // Check if levels already exist in output directory (avoid overwriting user-edited levels)
    for (int i = 1; i <= 20; ++i) {
        std::string filename = outputDirectory + "/level_" + (i < 10 ? "0" : "") + std::to_string(i) + ".json";
        if (!std::filesystem::exists(filename)) {
            // At least one level missing, proceed with import
            goto import_levels;
        }
    }
    // All 20 levels already exist, skip import - user has edited levels
    return true;

import_levels:
    try {
        std::ifstream is(intermediateJsonPath);
        if (!is.is_open()) return false;

        AuthFile file;
        try {
            cereal::JSONInputArchive archive(is);
            archive(cereal::make_nvp("levels", file.levels));
        } catch (const std::exception&) {
            return false;
        }
        if (file.levels.empty()) return false;

        std::filesystem::create_directories(outputDirectory);

        // Collect all models across all levels into a global models vector
        std::vector<ModelData> allModels;
        int nextModelId = 0;

        for (const auto& srcLevel : file.levels) {
            if (srcLevel.id < 1 || srcLevel.id > 20 || srcLevel.rooms.empty()) continue;

            LevelData lvl;
            lvl.level_id = srcLevel.id;
            lvl.name = "Level " + std::to_string(srcLevel.id);
            lvl.wall_r = kLevelPalettes[srcLevel.id - 1][0];
            lvl.wall_g = kLevelPalettes[srcLevel.id - 1][1];
            lvl.wall_b = kLevelPalettes[srcLevel.id - 1][2];
            lvl.start_room = 0;

            // Temporary vector for this level's models (for connectivity checks)
            std::vector<ModelData> levelModels;
            int roomIdx = 0;
            for (const auto& srcRoom : srcLevel.rooms) {
                if ((int)srcRoom.grid.size() < 12) continue;

                // Create model for this room
                ModelData model;
                model.name = "Level " + std::to_string(srcLevel.id) + " Room " + std::to_string(roomIdx + 1);
                model.width = 16;
                model.height = 12;
                model.tiles.assign(16 * 12, (int)TileType::AIR);

                // Decode structure with 19 -> 16 column compression
                static const std::map<char, int> charToTile = {
                    {'#', (int)TileType::SOLID_WALL},
                    {'F', (int)TileType::FRAGILE_WALL},
                    {'M', (int)TileType::REINFORCED_WALL},
                    {'~', (int)TileType::LAVA},
                };

                for (int y = 0; y < 12; ++y) {
                    const std::string& srcLine = srcRoom.grid[y];
                    for (int x = 0; x < 16; ++x) {
                        char ch = SrcCol(x) < (int)srcLine.size() ? srcLine[SrcCol(x)] : '.';
                        auto it = charToTile.find(ch);
                        if (it != charToTile.end()) {
                            model.tiles[y * 16 + x] = it->second;
                        }
                    }
                }

                // Solid borders with preserved shaft openings from the map
                auto borderIsOpen = [&](int y, int x) {
                    if (y == 0) return Passable(srcRoom.grid[0][SrcCol(x)]) && Passable(srcRoom.grid[1][SrcCol(x)]) && Passable(srcRoom.grid[2][SrcCol(x)]);
                    if (y == 11) return Passable(srcRoom.grid[11][SrcCol(x)]) && Passable(srcRoom.grid[10][SrcCol(x)]) && Passable(srcRoom.grid[9][SrcCol(x)]);
                    if (x == 0) return Passable(srcRoom.grid[y][0]) && Passable(srcRoom.grid[y][1]) && Passable(srcRoom.grid[y][2]);
                    if (x == 15) return Passable(srcRoom.grid[y][18]) && Passable(srcRoom.grid[y][17]) && Passable(srcRoom.grid[y][16]);
                    return false;
                };
                for (int x = 0; x < 16; ++x) {
                    model.tiles[x] = borderIsOpen(0, x) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                    model.tiles[11 * 16 + x] = borderIsOpen(11, x) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                }
                for (int y = 1; y < 11; ++y) {
                    model.tiles[y * 16] = borderIsOpen(y, 0) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                    model.tiles[y * 16 + 15] = borderIsOpen(y, 15) ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
                }

                // Guard against degenerate hollow bands
                int solids = 0;
                for (int t : model.tiles) {
                    if (t == (int)TileType::SOLID_WALL) solids++;
                }
                if (solids < 30) {
                    for (int y = 1; y < 11; ++y) {
                        model.tiles[y * 16] = (int)TileType::SOLID_WALL;
                        model.tiles[y * 16 + 15] = (int)TileType::SOLID_WALL;
                    }
                    int cx = 7 + (roomIdx % 2);
                    model.tiles[cx] = (int)TileType::AIR;
                    model.tiles[11 * 16 + cx] = (int)TileType::AIR;
                }

                // Connectivity: stacked rooms must link vertically
                if (roomIdx > 0 && !levelModels.empty()) {
                    auto& prevModel = levelModels.back();
                    std::vector<int> prevOpen;
                    for (int x = 0; x < 16; ++x) {
                        if (prevModel.tiles[11 * 16 + x] == (int)TileType::AIR) prevOpen.push_back(x);
                    }
                    bool linked = false;
                    for (int x : prevOpen) {
                        if (model.tiles[x] == (int)TileType::AIR) linked = true;
                    }
                    if (!linked) {
                        if (!prevOpen.empty()) {
                            for (int x : prevOpen) model.tiles[x] = (int)TileType::AIR;
                        } else {
                            for (int x = 7; x <= 8; ++x) {
                                prevModel.tiles[11 * 16 + x] = (int)TileType::AIR;
                                model.tiles[x] = (int)TileType::AIR;
                            }
                        }
                    }
                }

                model.id = nextModelId;
                levelModels.push_back(model);
                allModels.push_back(model);

                // Create room referencing this model
                RoomData room;
                room.room_id = roomIdx;
                room.model_id = nextModelId;
                room.room_x = 0;
                room.room_y = roomIdx;
                nextModelId++;

                // Entities detected in the map art
                int enemyCount = 0;
                for (const auto& ent : srcRoom.entities) {
                    float ex = (float)ent.col + 0.5f;
                    float ey = (float)ent.row + 0.4f;

                    if (roomIdx == 0 && ent.kind == "H") {
                        continue;
                    }

                    EnemyData ed;
                    bool isEnemy = true;
                    switch (ent.kind[0]) {
                        case 'v': ed.type = (int)hero::EnemyType::SNAKE; break;
                        case 's': ed.type = (int)hero::EnemyType::SPIDER; break;
                        case 'P': ed.type = (int)hero::EnemyType::BAT; break;
                        default: isEnemy = false; break;
                    }

                    if (isEnemy && enemyCount < 3 && ent.row >= 2 && ent.row <= 10) {
                        if (roomIdx == (int)srcLevel.rooms.size() - 1 && ent.row >= 6 &&
                            (ed.type == (int)hero::EnemyType::SNAKE || ed.type == (int)hero::EnemyType::BAT) &&
                            ent.col >= 10) {
                            lvl.miner_room = roomIdx;
                            lvl.miner_x = ex;
                            lvl.miner_y = ey;
                            isEnemy = false;
                        }
                    } else {
                        isEnemy = false;
                    }

                    if (isEnemy) {
                        ed.x = ex;
                        ed.y = ey;
                        ed.range_min = std::max(0.0f, ex - 3.0f);
                        ed.range_max = std::min(15.0f, ex + 3.0f);
                        ed.speed = 1.0f + (srcLevel.id % 5) * 0.15f;
                        ed.dir = (enemyCount % 2 == 0) ? 1 : -1;
                        room.enemies.push_back(ed);
                        enemyCount++;
                    } else if (ent.kind == "L") {
                        LampData lamp;
                        lamp.x = ex;
                        lamp.y = (float)ent.row + 0.5f;
                        lamp.lit = true;
                        room.lamps.push_back(lamp);
                    }
                }

                lvl.rooms.push_back(room);
                roomIdx++;
            }

            // Defaults if detection missed the miner
            if (lvl.miner_room == 0 && lvl.rooms.size() > 1) {
                lvl.miner_room = (int)lvl.rooms.size() - 1;
                lvl.miner_x = 13.0f;
                lvl.miner_y = 9.9f;
            }

            std::string filename = outputDirectory + "/level_" +
                                   (srcLevel.id < 10 ? "0" : "") + std::to_string(srcLevel.id) + ".json";
            SaveLevelToFile(lvl, filename);
            std::cout << "Imported authentic stage " << srcLevel.id << " (" << lvl.rooms.size() << " rooms)" << std::endl;
        }

        // Save all models to models/models.json
        std::string modelsDir = outputDirectory + "/models";
        std::filesystem::create_directories(modelsDir);
        SaveModelsToFile(allModels, modelsDir + "/models.json");

        return true;
    } catch (const std::exception& e) {
        std::cerr << "ImportAuthenticMaps failed: " << e.what() << std::endl;
        return false;
    }
}

} // namespace hero
