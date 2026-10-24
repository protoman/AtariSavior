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
#include <algorithm>
#include <fstream>
#include <iostream>
#include <filesystem>
#include <map>
#include <set>
#include <vector>
#include <sstream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace hero {

// ---------------------------------------------------------------------------
// Async walls moved from MODEL to ROOM (2026-10-17). Mirrors
// tools/migrate_async_to_rooms.py so the editor and the CLI agree.
// ---------------------------------------------------------------------------
namespace {
constexpr int kPhaseTile = 10;
constexpr int kVcrunchTile = 11;
constexpr int kHcrunchTile = 12;
constexpr int kSolidWall = 1;
// kRoomWidth lives in LevelData.hpp (shared with the exit-span constants).

bool IsFeatureTile(int t) {
    return t == kPhaseTile || t == kVcrunchTile || t == kHcrunchTile;
}

// model id -> {patches, feature cells} harvested from the legacy fields.
struct LegacyAsync {
    std::vector<std::vector<int>> patches;
    std::vector<std::vector<int>> features;
};
}  // namespace

bool DataSerializer::MigrateAsyncToRooms(std::vector<ModelData>& models,
                                         const std::string& levelsDir,
                                         const std::string& modelsPath) {
    namespace fs = std::filesystem;
    std::map<int, LegacyAsync> legacy;
    for (const auto& m : models) {
        LegacyAsync a;
        a.patches = m.asym_patches;
        const int w = m.width > 0 ? m.width : kRoomWidth;
        for (size_t i = 0; i < m.tiles.size(); ++i) {
            if (IsFeatureTile(m.tiles[i])) {
                a.features.push_back({static_cast<int>(i) / w,
                                      static_cast<int>(i) % w, m.tiles[i]});
            }
        }
        if (!a.patches.empty() || !a.features.empty()) {
            legacy[m.id] = a;
        }
    }
    if (legacy.empty()) {
        return false;                       // already migrated (or no async)
    }

    bool changed = false;
    std::error_code ec;
    std::vector<fs::path> levels;
    if (fs::is_directory(levelsDir, ec)) {
        for (const auto& e : fs::directory_iterator(levelsDir, ec)) {
            const std::string name = e.path().filename().string();
            if (name.rfind("level_", 0) == 0 && e.path().extension() == ".json") {
                levels.push_back(e.path());
            }
        }
    }
    std::sort(levels.begin(), levels.end());
    for (const auto& path : levels) {
        LevelData level;
        if (!LoadLevelFromFile(level, path.string())) {
            std::cerr << "migrate: cannot load " << path << std::endl;
            continue;
        }
        bool touched = false;
        for (auto& room : level.rooms) {
            const auto it = legacy.find(room.model_id);
            if (it == legacy.end()) {
                continue;
            }
            if (!it->second.patches.empty() && room.asym_patches.empty()) {
                room.asym_patches = it->second.patches;
                touched = true;
            }
            if (!it->second.features.empty() && room.feature_cells.empty()) {
                room.feature_cells = it->second.features;
                touched = true;
            }
        }
        if (touched && SaveLevelToFile(level, path.string())) {
            std::cout << "migrate: " << path.filename()
                      << " async walls moved to rooms" << std::endl;
            changed = true;
        }
    }

    for (auto& m : models) {
        if (!m.asym_patches.empty()) {
            m.asym_patches.clear();
            changed = true;
        }
        const int w = m.width > 0 ? m.width : kRoomWidth;
        for (size_t i = 0; i < m.tiles.size(); ++i) {
            if (IsFeatureTile(m.tiles[i])) {
                m.tiles[i] = kSolidWall;    // same PF byte (feature = solid)
                changed = true;
            }
        }
    }
    if (changed && !modelsPath.empty()) {
        SaveModelsToFile(models, modelsPath);   // persist the cleared models
    }
    return changed;
}

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
        MigrateToFourBands(models, nullptr);   // N=4: 3-row files open 4-band
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load models from " << filepath << ": " << e.what() << std::endl;
        return false;
    }
}

// ---------------------------------------------------------------------------
// Unified stage file (E1 2026-10-20): models + every level in ONE json.
// ---------------------------------------------------------------------------
namespace {
// cereal's class-version mechanism throws when `cereal_class_version` is
// absent, so a hand-written or generator-emitted stage file would lose the
// optional level fields (miner_dir). Inject the key into every level object
// (elements of the top-level `levels` array) when the file has none.
std::string VersionStageLevels(const std::string& json) {
    if (json.find("\"cereal_class_version\"") != std::string::npos) {
        return json;
    }
    const size_t key = json.find("\"levels\"");
    if (key == std::string::npos) return json;
    const size_t start = json.find('[', key);
    if (start == std::string::npos) return json;

    std::vector<size_t> inserts;   // positions right after each level's '{'
    int depth = 0;
    bool inString = false;
    bool escape = false;
    for (size_t i = start + 1; i < json.size(); ++i) {
        const char c = json[i];
        if (inString) {
            if (escape) {
                escape = false;
            } else if (c == '\\') {
                escape = true;
            } else if (c == '"') {
                inString = false;
            }
            continue;
        }
        if (c == '"') {
            inString = true;
        } else if (c == '{') {
            if (depth == 0) inserts.push_back(i + 1);
            ++depth;
        } else if (c == '}') {
            --depth;
        } else if (c == ']' && depth == 0) {
            break;
        }
    }
    std::string out = json;
    // Back to front so the earlier offsets stay valid.
    for (auto it = inserts.rbegin(); it != inserts.rend(); ++it) {
        out.insert(*it, "\n\"cereal_class_version\": 1,");
    }
    return out;
}
}  // namespace

bool DataSerializer::SaveStageToFile(const std::vector<LevelData>& levels,
                                     const std::vector<ModelData>& models,
                                     const std::string& filepath) {
    try {
        std::ofstream os(filepath);
        if (!os.is_open()) return false;
        cereal::JSONOutputArchive archive(os);
        StageFile stage;
        stage.models = models;
        stage.levels = levels;
        archive(cereal::make_nvp("stage", stage));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to save stage to " << filepath << ": "
                  << e.what() << std::endl;
        return false;
    }
}

void DataSerializer::MigrateToFourBands(std::vector<ModelData>& models,
                                        std::vector<LevelData>* levels) {
    // 1. Collect, per model, the single M1 strip column that every room using
    //    it agrees on (-1 = rooms disagree / no strip). The strip is a
    //    WHOLE-CAVE latch (ENAM1), so its column must be wall-or-patched in
    //    EVERY band; the inserted AIR band would expose it.
    std::map<int, int> m1Col;
    std::map<int, int> gained;   // model id -> 1 when a band was inserted
    if (levels) {
        for (const auto& level : *levels) {
            for (const auto& room : level.rooms) {
                std::set<int> cols;
                for (const auto& p : room.asym_patches) {
                    if (p.size() == 4 && p[3] == 1) cols.insert(p[1]);
                }
                // A room with NO strip does not constrain the column: only the
                // rooms that paint one must agree (the extra wall it adds in
                // the new band is verified by the connectivity guard below).
                if (cols.empty()) continue;
                const int col = cols.size() == 1 ? *cols.begin() : -1;
                auto it = m1Col.find(room.model_id);
                if (it == m1Col.end()) m1Col[room.model_id] = col;
                else if (it->second != col) it->second = -1;
            }
        }
    }

    // 2. Pad every 3-row model to [row0, row1, AIR, row2].
    for (auto& m : models) {
        const int w = m.width > 0 ? m.width : kRoomWidth;
        if (m.height != 3 || (int)m.tiles.size() != w * 3) continue;
        std::vector<int> next(m.tiles.begin(), m.tiles.begin() + 2 * w);
        next.insert(next.end(), w, (int)TileType::AIR);
        next.insert(next.end(), m.tiles.begin() + 2 * w, m.tiles.end());
        m.tiles = std::move(next);
        m.height = 4;
        gained[m.id] = 1;
    }
    if (!levels || gained.empty()) return;

    // 3. Hide the strip in the inserted band when the authored model already
    //    has that column SOLID in every band the strip does not cross (the
    //    generator's side-gate door). Repeating the wall cannot seal a
    //    corridor: the column is solid above and below the door band already.
    //    A ladder-style strip (open above/below, e.g. the live stage's L1R2)
    //    is left alone — that is a per-room authoring call (patch or wall).
    for (auto& m : models) {
        auto it = m1Col.find(m.id);
        if (it == m1Col.end() || it->second < 0 || !gained.count(m.id)) {
            continue;
        }
        const int w = m.width > 0 ? m.width : kRoomWidth;
        const int col = it->second;
        if (col >= w || (int)m.tiles.size() != w * 4) continue;
        bool solidAround = true;
        for (int band : {0, 3}) {
            const int t = m.tiles[band * w + col];
            if (t == (int)TileType::AIR) { solidAround = false; break; }
        }
        if (solidAround) m.tiles[2 * w + col] = (int)TileType::SOLID_WALL;
    }

    // 4. Authored rows ride the model: the old bottom row is band 3 now.
    for (auto& level : *levels) {
        for (auto& room : level.rooms) {
            if (!gained.count(room.model_id)) continue;
            for (auto& p : room.asym_patches) {
                if (!p.empty() && p[0] == 2) p[0] = 3;
            }
            for (auto& f : room.feature_cells) {
                if (!f.empty() && f[0] == 2) f[0] = 3;
            }
        }
    }

    // 5. Anything the auto-hide could not decide is the author's call.
    for (auto& level : *levels) {
        for (auto& room : level.rooms) {
            if (!gained.count(room.model_id)) continue;
            auto it = m1Col.find(room.model_id);
            const bool hidden = it != m1Col.end() && it->second >= 0;
            if (!hidden) {
                for (const auto& p : room.asym_patches) {
                    if (p.size() == 4 && p[3] == 1) {
                        std::cerr << "migrate: model " << room.model_id
                                  << " (room " << room.room_id << "): the "
                                     "M1 strip is drawn in EVERY band, so "
                                     "band 2 col " << p[1] << " must be "
                                     "WALL or carry an M1 patch (otherwise "
                                     "a 1 px line shows in the new air "
                                     "band)" << std::endl;
                    }
                }
            }
        }
    }
}

bool DataSerializer::LoadStageFromFile(std::vector<LevelData>& levels,
                                       std::vector<ModelData>& models,
                                       const std::string& filepath) {
    std::string json;
    try {
        std::ifstream is(filepath);
        if (!is.is_open()) return false;
        json.assign((std::istreambuf_iterator<char>(is)),
                    std::istreambuf_iterator<char>());
    } catch (const std::exception& e) {
        std::cerr << "Failed to read stage " << filepath << ": " << e.what()
                  << std::endl;
        return false;
    }
    const std::string versioned = VersionStageLevels(json);
    // Canonical form first ({"stage": {...}}), then the bare form.
    try {
        std::istringstream input(versioned);
        cereal::JSONInputArchive archive(input);
        StageFile stage;
        archive(cereal::make_nvp("stage", stage));
        levels = stage.levels;
        models = stage.models;
        MigrateToFourBands(models, &levels);
        return true;
    } catch (const cereal::Exception&) {
        // fall through to the bare form
    } catch (const std::exception&) {
        // fall through too — the bare attempt reports the real error
    }
    try {
        std::istringstream input(versioned);
        cereal::JSONInputArchive archive(input);
        StageFile stage;
        archive(stage);
        levels = stage.levels;
        models = stage.models;
        MigrateToFourBands(models, &levels);
        return true;
    } catch (const std::exception& e) {
        std::cerr << "Failed to load stage from " << filepath << ": "
                  << e.what() << std::endl;
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

// ---------------------------------------------------------------------------
// E2 (2026-10-20): the 20-LEVEL STAGE GENERATOR.
//
// Goal: level n has n rooms (1..20 = 210 rooms) at a ROM cost the C7 level-data
// split can hold. The cost lever is SHARED MODEL SHAPES: the converter emits
// one shape block per REFERENCED model id, so 210 rooms must resolve to a
// handful of shapes instead of one model per room (the retired
// GenerateAll20DefaultLevels built a fresh 60-tile model per room).
//
// SHAPE LIBRARY — keyed by the CARVED exits, three bits only:
//   SHAPE_N / SHAPE_S  room above / below  (every vertical pair is a corridor)
//   SHAPE_H            the mirrored horizontal opening (west AND east) is cut
// West and east share ONE bit on purpose: the playfield is REFLECTED, so cell 0
// (the room's outer edge) is drawn on both sides of the room and collision
// mirrors too (PlayerHitsMap maps display col >= 20 to 39-col). There is no
// way to cut only one side — and two models differing only in "which side"
// would be byte-identical anyway (the converter still counts them separately).
//
// LAYOUT — a 2-column serpentine, mirror-safe:
//   level n <= 10 : x=0, y=0..n-1                   (pure vertical corridor)
//   level n >  10 : x=0, y=0..9, the turn, then x=1, y=9 -> 10-m going UP
// Exits are DERIVED FROM ADJACENCY at run time (C1: bank2 ExitScanB2 scans the
// stored position column), so the carve MUST agree with the neighbour set:
//   * every vertically adjacent pair is carved on BOTH sides;
//   * horizontally, both columns are occupied on many rows, so every such pair
//     is WALLED (solid col 0 / row 1 in both models): the ROM still sees the
//     adjacency, but the player can never reach the edge to use it;
//   * the ONE carved horizontal pair is the turn, and both of its rooms carry
//     SHAPE_H — a one-sided carve would drop the player inside the neighbour's
//     wall (EnterRoom places him at x=4 = that room's col 0).
// The turn rooms also show a dead aperture on their far side (nobody there):
// the exit scan finds no room (bank2 ExitNoneB2) and the player stops at the
// edge. That is the only layout artefact, and it cannot tear a transition.
//
// Deterministic BY CONSTRUCTION: no RNG, no clock, no unordered container; the
// model ids are the ascending shape keys and rooms are emitted in walk order,
// so two runs are byte-identical (tools/test_generator.py asserts it).
// ---------------------------------------------------------------------------
namespace {

constexpr int kStageLevels = 20;     // level n = 1..20
constexpr int kGridW = 5;            // layout lattice (positions are 4-bit)
constexpr int kGridH = 5;
// Exit bits + hazard bits (2026-10-20: the generated stage got its HERO-style
// variety — hot bands, a keyed gate, water goals with raft/tentacle).
enum ShapeBits {
    SHAPE_N = 1,
    SHAPE_S = 2,
    SHAPE_H = 4,
    SHAPE_START = 8,
    SHAPE_HOT = 16,      // row-1 walls hot (model mid_band_type = 1)
    SHAPE_GATE = 32,     // row-1 wall with ONE open gap (door / gate column)
    SHAPE_WATER = 64,    // row-2 open water (bottom band, raft/tentacle)
    SHAPE_2GAP = 128,    // TWO vertical gaps (cells 3 and 6) instead of the
                         // centre 8-9: the next room must repeat the pair
    SHAPE_CHANNEL = 256, // HERO-style water crossing: hot row-1 ceiling
                         // (cells 1..7), low channel over the water, raft
    // User rule 2026-10-21: no room may be a straight vertical fall. From
    // level 6 every LINK is NARROW (one corridor cell) or WIDE (both), and
    // consecutive links alternate, so each through-room has a different number
    // of exits at the top and the bottom and the player has to line up.
    SHAPE_N1 = 1 << 13,  // narrow TOP opening (cell vA only)
    SHAPE_S1 = 1 << 14   // narrow BOTTOM opening
};
constexpr int kGateCol = 4;          // the gate/door cell in row 1
constexpr int kGapA = 3;             // 2-gap columns (model cells)
constexpr int kGapB = 6;
// Archetype interior (HERO-like variety for ordinary/hot rooms): 3 bits in
// the mask, applied AFTER the exits/hazards. Ids 1..5 = normal families,
// 6..8 = hot families. Only cells 1..7 are ever touched (0 = H exit, 8/9 =
// the vertical shaft), and the 2-gap cells are re-opened afterwards.
constexpr int kArchShift = 9;
constexpr int kArchMask = 15;   // 4 bits: hot archetypes use ids 8..14
// Shape budget: extra archetype variants are enabled ONLY while the library
// fits. The base schedule is 40 shapes (the current bank3 slot); after the
// two-slot split raises the shape slot, bump this (tools/bank3_data_sizes.py
// reports the headroom). With the budget at the current count the generator
// output is byte-identical to the pre-budget build.
// Shape budget = the 6-bit index cap (64). The maze layout multiplies the
// exit signatures (N/S/H x 2Gap x narrow-gap), so the archetype count is
// the knob that is spent first (Build20LevelStage picks the widest set
// that fits). Measured 2026-10-24: 63 shapes, bank3 shapes window fits
// with the test_generator slack gate green.
constexpr int kShapeBudget = 64;
const char* const kArch[8][3] = {
    {"..........", "..........", ".........."},          // 0 shaft
    {"..###.....", "..........", ".....###.."},          // 1 ledge ladder
    {"..........", "...#.#....", ".........."},          // 2 pillars
    {"...#......", "....#.....", ".........."},          // 3 steps
    {"......#...", "......##..", ".........."},          // 4 side pocket
    {"..##......", ".....#....", "......##.."},          // 5 zigzag
    // extra families (shape-budget mode only)
    {".#.#......", "..#..#....", "......#.#."},          // 6 spiral
    {"..#.......", "..#..#....", ".......#.."},          // 7 gallery
};
// Hot archetypes must SHAPE THE PATH (user 2026-10-21): every one blocks the
// centre (cells 8/9 = the vertical shaft) and forces a detour through an
// offset gap. Ids 8..14.
const char* const kArchHot[7] = {
    "#####.####",   // 8  gate: one gap at cell 5 (the shaft is hot)
    "###.##.###",   // 9  split: gaps at 3 and 6 (choose)
    "#.#.#.#.##",   // 10 comb: weave through 1/3/5/7
    "##.#######",   // 11 align (>level 10): single offset gap at cell 2
    "##.####.##",   // 12 twin gaps at 2 and 7 (budget)
    "#.####.###",   // 13 stairs: gaps at 1 and 6 (budget)
    "####.#####",   // 14 HOT START: the drop column (cell 4) stays open,
                    //    else the spawn lands on a hot wall (budget mode)
};
const int kArchHotGapX[7] = {10, 6, 10, 4, 4, 2, 8};   // cell*2
// The miner must STAND on a solid block (user rule 2026-10-21: a person to
// rescue does not swim/fly). miner_x is in CELL units: the converter turns it
// into display col `miner_x * 2` (8 px per cell), so cell 4 = px 32 and the
// mirrored cell (editor x 15) = px 120. The water-goal rock sits on cell 4 in
// the half-model, which the reflected playfield also draws on the right.
const int kMinerCell = 4;
const float kMinerX = (float)kMinerCell;      // display col 8  (px 32)
const float kMinerFarX = 15.0f;               // display col 30 (px 120)
const char* const kArchName[15] = {
    "", "Ladder", "Pillars", "Steps", "Pocket", "Zigzag", "Spiral",
    "Gallery", "HotGate", "HotSplit", "HotComb", "HotAlign", "HotTwin",
    "HotStair", "HotDrop"};
// Base choices vs budget-enabled choices (ids).
const int kNormalBase[5] = {1, 2, 3, 4, 5};
const int kNormalExtra[7] = {1, 2, 3, 4, 5, 6, 7};
const int kHotBase[3] = {8, 9, 10};
const int kHotLate[4] = {8, 9, 10, 11};
const int kHotExtra[6] = {8, 9, 10, 11, 12, 13};

// Grid cell of a room in the level (x = column, y = row; rooms at the same y
// in different columns are horizontally adjacent and therefore "connected"
// as far as the ROM is concerned).
struct GridPos {
    int x = 0;
    int y = 0;
};
bool HasRoomAt(const std::vector<GridPos>& walk, int x, int y);

// The CHANNEL room (water crossing from level 11): a hot row-1 ceiling forces
// the player down to the low channel, where the raft crosses the water to the
// side exit (HERO-like). It needs a room that runs LEFT-RIGHT (a side
// neighbour on each side), and it must not be the goal (the miner would stand
// in the water). With the maze layout the room is chosen by distance to the
// goal: the LAST room with both side neighbours.
bool IsChannelRoom(int level, const std::vector<GridPos>& walk,
                   const GridPos& pos) {
    if (level < 11 || walk.size() < 3) return false;
    const GridPos& goal = walk.back();
    if (pos.x == goal.x && pos.y == goal.y) return false;
    if (!HasRoomAt(walk, pos.x - 1, pos.y)
            || !HasRoomAt(walk, pos.x + 1, pos.y)) {
        return false;
    }
    // Nearest to the goal wins (deterministic: the first in row-major order).
    const int want = std::abs(pos.x - goal.x) + std::abs(pos.y - goal.y);
    for (const GridPos& other : walk) {
        if (&other == &pos) continue;
        if (other.x == goal.x && other.y == goal.y) continue;
        if (!HasRoomAt(walk, other.x - 1, other.y)
                || !HasRoomAt(walk, other.x + 1, other.y)) {
            continue;
        }
        const int d = std::abs(other.x - goal.x) + std::abs(other.y - goal.y);
        if (d < want || (d == want
                && (other.y < pos.y || (other.y == pos.y && other.x < pos.x)))) {
            return false;
        }
    }
    return true;
}

std::string ShapeName(int mask) {
    if (mask == 0) {
        return "Sealed";
    }
    std::string name;
    auto add = [&name](const char* part) {
        name += name.empty() ? part : std::string("+") + part;
    };
    if (mask & SHAPE_N) add((mask & SHAPE_N1) ? "n" : "N");
    if (mask & SHAPE_S) add((mask & SHAPE_S1) ? "s" : "S");
    if (mask & SHAPE_H) add("H");
    if (mask & SHAPE_START) add("Start");
    if (mask & SHAPE_GATE) add("Gate");
    if (mask & SHAPE_WATER) add("Water");
    if (mask & SHAPE_CHANNEL) add("Channel");
    if (mask & SHAPE_2GAP) add("2Gap");
    const int arch = (mask >> kArchShift) & kArchMask;
    if (arch) add(kArchName[arch]);
    return name;
}

// SIZE: the E2 stage generator still speaks THREE bands (its plans, exits and
// QA expectations are built around 3 bands / 3 rows). The editor grid and
// every loaded/saved model are 4 bands (kRoomHeight); a generated 3-row model
// is migrated to [r0, r1, AIR, r2] on load, exactly like any legacy file.
constexpr int kGenRows = 3;

ModelData MakeShapeModel(int modelId, int mask) {
    ModelData model;
    model.id = modelId;
    model.name = "Shape " + ShapeName(mask);
    model.width = kRoomWidth;
    model.height = kGenRows;
    model.tiles.assign(kRoomWidth * kGenRows, (int)TileType::AIR);
    // Border walls: rows 0 and 2 are full bands (a floor/ceiling row), and the
    // middle band's only wall is COL 0 — the mirrored OUTER edge. Col 9 is the
    // centre seam, NOT a boundary: a solid cell there would split the middle
    // band into two chambers and choke the vertical shaft (the live rooms keep
    // it open too: row 1 = "#.........").
    for (int x = 0; x < kRoomWidth; ++x) {
        model.tiles[x] = (int)TileType::SOLID_WALL;                    // row 0
        model.tiles[(kGenRows - 1) * kRoomWidth + x] =
            (int)TileType::SOLID_WALL;                                 // row 2
    }
    for (int y = 0; y < kGenRows; ++y) {
        model.tiles[y * kRoomWidth] = (int)TileType::SOLID_WALL;        // col 0
    }

    if (mask & SHAPE_N) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[x] = (int)TileType::AIR;
    }
    if (mask & SHAPE_S) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
    }
    if (mask & SHAPE_H) {
        // N=4: open the side in every WALKABLE band (row 1..height-2);
        // a 3-row plan model only has band 1 there.
        for (int y = kHorizExitA;
             y <= std::min(kHorizExitB, kGenRows - 2); ++y)
            model.tiles[y * kRoomWidth + kHorizExitCol] = (int)TileType::AIR;
    }
    if (mask & SHAPE_START) {
        // Level start rooms: the kernel drops the player in at LevelStartX/Y =
        // (32, 24) px = display col 8 = CELL 4 of the TOP band, and DropStep
        // bypasses collision — a solid band there would drop him INSIDE a wall.
        // Open cells 2..6 (the drop slot); 7..9 stay solid so an async block
        // can sit at row 1 col 7 (the M1 column must be walled in the other
        // bands, 2026-10-21).
        for (int x = 2; x <= 6; ++x)
            model.tiles[x] = (int)TileType::AIR;
    }
    if (mask & SHAPE_HOT) {
        // HERO-style hot band: two symmetric wall blocks narrow the middle
        // band, the shaft keeps cells 1/4/5/8/9. mid_band_type = 1 makes
        // convert promote every row-1 wall to H (solid + lethal touch).
        for (int x : {2, 3, 6, 7}) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        model.mid_band_type = 1;
    }
    if (mask & SHAPE_GATE) {
        // Keyed gate: row 1 is a wall except the room's VERTICAL CORRIDOR,
        // which is where the door patches sit. A gap anywhere else is
        // unreachable — the player descends through the corridor cells, and a
        // door at cell 4 while the exits are 8/9 (or 3/6) soft-locked the
        // level (user report 2026-10-21: level 13 room 4 could not be passed).
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        // ONE door cell: the M1 patch strip allows a single column per side,
        // and the door must be the only way down (the other corridor cell
        // stays a wall, a dead-end niche from band 0/2).
        const int doorCell = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        model.tiles[1 * kRoomWidth + doorCell] = (int)TileType::AIR;
    }
    if (mask & SHAPE_2GAP) {
        // Two vertical gaps: the pair is repeated in the ceiling and the
        // floor, so a room below inherits BOTH openings. START rooms keep
        // their drop opening in the top band (the drop is not an exit).
        if (mask & SHAPE_N) {
            for (int x = 0; x < kRoomWidth; ++x) model.tiles[x] =
                (int)TileType::SOLID_WALL;
            model.tiles[kGapA] = model.tiles[kGapB] = (int)TileType::AIR;
            if ((mask & SHAPE_GATE) && (mask & SHAPE_2GAP)) {
            // A two-gap ceiling reaches the door through band 0: the top
            // corridor is a lobby, so an entry arriving at the OTHER gap still
            // finds the door. (The south edge keeps only the two carved cells
            // — widening it would drop the player into the next room's wall.)
            for (int x = kGapA; x <= kGapB; ++x) {
                model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_START) {
                for (int x = 2; x <= 6; ++x)
                    model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            for (int x = 0; x < kRoomWidth; ++x) model.tiles[base + x] =
                (int)TileType::SOLID_WALL;
            model.tiles[base + kGapA] = model.tiles[base + kGapB] =
                (int)TileType::AIR;
        }
    }
    if (mask & SHAPE_CHANNEL) {
        // Hot ceiling cells 1..7; cells 8/9 stay the N shaft, cell 0 is the
        // H exit. The floor is open water: crossing low on the raft is the
        // only safe route (row 1 is lethal wall).
        for (int x = 1; x <= 7; ++x) {
            model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
        }
        model.mid_band_type = 1;
        if (mask & SHAPE_2GAP) {
            // The 2-gap ceiling above must drop INTO the channel, not onto a
            // hot cell: open the same two cells in the hot row.
            model.tiles[1 * kRoomWidth + kGapA] = (int)TileType::AIR;
            model.tiles[1 * kRoomWidth + kGapB] = (int)TileType::AIR;
        }
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
        }
    }
    if (mask & SHAPE_WATER) {
        // Water goal: the bottom band is open, so the water strip shows and
        // kills; the miner waits on row 1 STANDING ON A ROCK (user rule
        // 2026-10-21 — a person to rescue does not swim or fly), and the raft
        // floats on another open cell so it never spawns inside the rock.
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[(kGenRows - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
        }
        model.tiles[(kGenRows - 1) * kRoomWidth + kMinerCell] =
            (int)TileType::SOLID_WALL;
    }
    // Archetype interior (HERO-like normality): cells 1..7 only, applied
    // AFTER the functional carving, then the 2-gap corridor is re-opened.
    const int arch = (mask >> kArchShift) & kArchMask;
    if (arch >= 1 && arch <= 7) {
        for (int row = 0; row < kGenRows; ++row) {
            for (int x = 0; x < kRoomWidth; ++x) {
                if (kArch[arch][row][x] == '#') {
                    model.tiles[row * kRoomWidth + x] =
                        (int)TileType::SOLID_WALL;
                }
            }
        }
    } else if (arch >= 8 && arch <= 14) {
        const char* pat = kArchHot[arch - 8];
        for (int x = 0; x < kRoomWidth; ++x) {
            if (pat[x] == '#') {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::SOLID_WALL;
            }
        }
        model.mid_band_type = 1;
    }
    // --- EXIT GEOMETRY + CONNECTIVITY (user rules 2026-10-21) -------------
    // PF walls are one pattern per 48-line band, so an entry only works if
    // band 1 is open on the same column. The generator now:
    //   * forces the carved edge cells (WIDE = both corridor cells, NARROW =
    //     one), which is what makes consecutive links alternate;
    //   * opens band 1 across the span between the top and bottom cells, so
    //     the player can LINE UP (the "space in the middle band" a dogleg
    //     room needs) — never a straight empty fall;
    //   * gives a horizontal room its aisle from cell 0;
    //   * lets a gate keep only the door column open in band 1.
    {
        const int vA = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int vB = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        std::vector<int> nCells, sCells;
        if (mask & SHAPE_N) {
            model.tiles[vA] = (int)TileType::AIR;
            nCells.push_back(vA);
            if (mask & SHAPE_N1) {
                model.tiles[vB] = (int)TileType::SOLID_WALL;
            } else {
                model.tiles[vB] = (int)TileType::AIR;
                nCells.push_back(vB);
            }
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            model.tiles[base + vA] = (int)TileType::AIR;
            sCells.push_back(vA);
            if (mask & SHAPE_S1) {
                model.tiles[base + vB] = (int)TileType::SOLID_WALL;
            } else {
                model.tiles[base + vB] = (int)TileType::AIR;
                sCells.push_back(vB);
            }
        }
        int lo = kRoomWidth, hi = -1;
        for (int c : nCells) { if (c < lo) lo = c; if (c > hi) hi = c; }
        for (int c : sCells) { if (c < lo) lo = c; if (c > hi) hi = c; }
        if (mask & SHAPE_GATE) {
            // The keyed door is the ONLY passage: band 1 keeps just the first
            // corridor cell (the door column).
            hi = lo;
        }
        if (hi >= lo) {
            for (int x = lo; x <= hi; ++x) {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_H) {
            const int near = (hi >= lo) ? lo : 0;
            for (int x = 0; x <= near; ++x) {
                model.tiles[1 * kRoomWidth + x] = (int)TileType::AIR;
            }
        }
        if ((mask & SHAPE_GATE) && (mask & SHAPE_2GAP)) {
            // Top lobby: an entry arriving at the other gap still finds the
            // door (the south edge keeps the carved cells; widening it would
            // drop the player into the next room's wall).
            for (int x = kGapA; x <= kGapB; ++x) {
                model.tiles[x] = (int)TileType::AIR;
            }
        }
        if (mask & SHAPE_START) {
            for (int x = 2; x <= vA; ++x) model.tiles[x] = (int)TileType::AIR;
        }
    }
    if (arch && (mask & SHAPE_2GAP)) {
        model.tiles[1 * kRoomWidth + kGapA] = (int)TileType::AIR;
        model.tiles[1 * kRoomWidth + kGapB] = (int)TileType::AIR;
        if (mask & SHAPE_N) {
            model.tiles[kGapA] = (int)TileType::AIR;
            if (!(mask & SHAPE_N1)) model.tiles[kGapB] = (int)TileType::AIR;
        }
        if (mask & SHAPE_S) {
            const int base = (kGenRows - 1) * kRoomWidth;
            model.tiles[base + kGapA] = (int)TileType::AIR;
            if (!(mask & SHAPE_S1)) {
                model.tiles[base + kGapB] = (int)TileType::AIR;
            }
        }
    }
    // --- NO DEAD AIR POCKETS (user rule 2026-10-21) -----------------------
    // A band-1 air cell that cannot be reached from any band-0/2 opening (or
    // from the horizontal exit) is decoration the player can never use — the
    // HotComb leftover at cells 7/8 was the reported "nothing to do here"
    // room. Close every such component; the corridor and the aisle always
    // anchor to an edge, so they are never touched.
    {
        bool ink[3][kRoomWidth] = {};
        for (int b = 0; b < kGenRows; ++b)
            for (int x = 0; x < kRoomWidth; ++x)
                ink[b][x] = model.tiles[b * kRoomWidth + x]
                                == (int)TileType::AIR;
        bool seen[3][kRoomWidth] = {};
        for (int x = 0; x < kRoomWidth; ++x) {
            for (int b : {1}) {
                if (!ink[b][x] || seen[b][x]) continue;
                bool anchored = false;
                std::vector<std::pair<int, int>> comp, stack{{b, x}};
                seen[b][x] = true;
                while (!stack.empty()) {
                    auto [y, c] = stack.back();
                    stack.pop_back();
                    comp.push_back({y, c});
                    if ((y == 1 && c == 0 && (mask & SHAPE_H)) ||
                        (y > 0 && ink[y - 1][c]) ||
                        (y < kGenRows - 1 && ink[y + 1][c])) {
                        anchored = true;
                    }
                    for (int dy : {-1, 0, 1}) {
                        for (int dx : {-1, 0, 1}) {
                            if (std::abs(dx) + std::abs(dy) != 1) continue;
                            const int ny = y + dy, nx = c + dx;
                            if (ny < 0 || ny >= kGenRows || nx < 0
                                    || nx >= kRoomWidth) continue;
                            if (!ink[ny][nx] || seen[ny][nx]) continue;
                            seen[ny][nx] = true;
                            stack.push_back({ny, nx});
                        }
                    }
                }
                if (!anchored) {
                    for (auto [y, c] : comp) {
                        model.tiles[y * kRoomWidth + c] =
                            (int)TileType::SOLID_WALL;
                    }
                }
            }
        }
    }

    // --- THIN WALLS (user rule 2026-10-21) --------------------------------
    // The bomb punch removes a THIN wall — a solid cell with air on both
    // sides — so a decorative 1-cell pillar is a pointless bomb target. A
    // generated wall must be a RUN: an isolated cell is thickened on a side
    // that carries no path (vertical corridor / horizontal aisle / start
    // drop); if both sides carry the path, the decoration is removed. The
    // intentional bombable blocks live on ROOMS (asym patches), never here.
    {
        const int pa = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int pb = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        const int near = pa < pb ? pa : pb;
        const bool start = (mask & SHAPE_START) != 0;
        const int startNear = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        // Is this cell part of a path the room needs (and so may not become
        // a wall)? The corridor spans every band; the horizontal aisle only
        // band 1; the spawn drop only bands 0/1.
        auto keep = [&](int band, int x) {
            if (x == pa || x == pb) return true;            // vertical corridor
            if ((mask & SHAPE_H) && band == 1 && x <= near) return true;
            if (start && band == 0 && x >= 2 && x <= startNear) return true;
            if (start && band == 1 && x == 4) return true;  // HotDrop column
            return false;
        };
        auto solid = [&](int band, int x) {
            return model.tiles[band * kRoomWidth + x]
                       != (int)TileType::AIR;
        };
        for (int band = 0; band < kGenRows; ++band) {
            for (int x = 1; x < kRoomWidth - 1; ++x) {
                if (!solid(band, x) || solid(band, x - 1)
                        || solid(band, x + 1)) {
                    continue;                     // part of a run
                }
                const bool leftFree = !keep(band, x - 1);
                const bool rightFree = !keep(band, x + 1);
                int cand = -1;
                if (leftFree && !rightFree) cand = x - 1;
                else if (rightFree && !leftFree) cand = x + 1;
                else if (leftFree && rightFree) cand = (x < 5) ? x - 1 : x + 1;
                if (cand >= 0) {
                    model.tiles[band * kRoomWidth + cand] =
                        model.tiles[band * kRoomWidth + x];
                } else {
                    model.tiles[band * kRoomWidth + x] = (int)TileType::AIR;
                }
            }
        }
    }
    // N=4 (2026-10-24): one row per drawn band. The plan is built in three
    // rows (0 ceiling / 1 shaft / 2 floor+water); band 2 is DERIVED as the
    // vertical route's continuation — open only at the room's exit columns
    // (3/6 for a two-gap shape, 8/9 otherwise), walls everywhere else. So the
    // cave has two real walkable bands with no inserted AIR pad, and every
    // other band-1 column stays WALLED in band 2: that wall is exactly what
    // the whole-cave M1 strip needs (a locked door / async block paints one
    // band and requires the others walled at its column), which is why band 2
    // is NOT a copy of band 1 — a copy left the block scan with no legal cell
    // and level 7 lost its async room entirely.
    // Every planned shape takes this path, including the SHAPE_GATE ones: with
    // locked doors disabled (PlanFor: p.gate = false) the only gate shapes are
    // the PHASE corridors, whose blink is a band-1 PF cell on the corridor
    // column — the same column band 2 keeps open — so the blink still gates the
    // whole passage and no M1 strip is involved. A real LOCKED DOOR would have
    // to come back here: its strip may only be painted on band 1 (2-patch cap)
    // while band 2 must stay open for the descent, which needs the landing
    // design (enter one side, cross the door, descend on the other).
    {
        const int routeA = (mask & SHAPE_2GAP) ? kGapA : kVertExitA;
        const int routeB = (mask & SHAPE_2GAP) ? kGapB : kVertExitB;
        std::vector<int> three = model.tiles;   // rows 0,1,2
        model.tiles.assign(kRoomWidth * 4, (int)TileType::AIR);
        for (int x = 0; x < kRoomWidth; ++x) {
            model.tiles[0 * kRoomWidth + x] = three[0 * kRoomWidth + x];
            model.tiles[1 * kRoomWidth + x] = three[1 * kRoomWidth + x];
            const bool route = (x == routeA || x == routeB)
                    && three[1 * kRoomWidth + x] == (int)TileType::AIR;
            model.tiles[2 * kRoomWidth + x] = route
                    ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
            model.tiles[3 * kRoomWidth + x] = three[2 * kRoomWidth + x];
        }
        model.height = 4;
    }
    return model;
}

// Deterministic integer mix: the layout's only source of (reproducible)
// variation. No RNG, no clock — two runs must be byte-identical.
unsigned LayoutMix(unsigned a, unsigned b) {
    unsigned h = a * 2654435761u ^ (b + 0x9E3779B9u);
    h ^= h >> 15;
    h *= 2246822519u;
    h ^= h >> 13;
    return h;
}

// LAYOUT (user rule 2026-10-24): the room GRID comes first, the exits follow
// from ADJACENCY (RoomShapeMask). A connected set of `rooms` cells is grown on
// a 5x5 lattice, then the GOAL room is moved to the end of the walk: it is the
// LEAF farthest from the start, because the miner stands there and the level
// ends by touching him — a goal room continues nowhere.
//
// Complexity RAMPS with the level (user rule 2026-10-24: the multi-block maze
// is a level-15+ shape of level; early levels stay corridors):
//   maxTouch 1 (levels < 6)  : a new cell may touch ONE placed cell -> corridor
//   maxTouch 2 (levels < 15) : a second touch is allowed -> one loop/branch
//   maxTouch 3 (levels 15+)  : free growth -> the drawn maze, where the
//                              approach to the goal can be reached two ways
std::vector<GridPos> LevelLayout(int level, int rooms) {
    const int n = rooms < 2 ? 2 : rooms;
    const int maxTouch = level < 6 ? 1 : (level < 15 ? 2 : 3);
    bool used[kGridH][kGridW] = {};
    std::vector<GridPos> walk;
    walk.reserve(n);
    used[0][0] = true;                  // the start room (top-left)
    walk.push_back(GridPos{0, 0});
    auto touch = [&](int x, int y) {
        int t = 0;
        if (x > 0 && used[y][x - 1]) ++t;
        if (x + 1 < kGridW && used[y][x + 1]) ++t;
        if (y > 0 && used[y - 1][x]) ++t;
        if (y + 1 < kGridH && used[y + 1][x]) ++t;
        return t;
    };
    for (int step = 1; step < n; ++step) {
        if (level < 6) {
            // Levels 1-5 are a straight vertical corridor (the ramp the
            // user asked for): the stem just keeps going down, which also
            // guarantees the hazard roles have a vertical room to host.
            const GridPos last = walk.back();
            const GridPos down{last.x, last.y + 1};
            if (down.y < kGridH) {
                used[down.y][down.x] = true;
                walk.push_back(down);
                continue;
            }
        }
        std::vector<GridPos> cand;
        for (int y = 0; y < kGridH; ++y) {
            for (int x = 0; x < kGridW; ++x) {
                if (used[y][x]) continue;
                const int t = touch(x, y);
                if (t == 0 || t > maxTouch) continue;
                cand.push_back(GridPos{x, y});
            }
        }
        if (cand.empty()) {             // ramp too tight: relax to any touch
            for (int y = 0; y < kGridH; ++y) {
                for (int x = 0; x < kGridW; ++x) {
                    if (!used[y][x] && touch(x, y) > 0) {
                        cand.push_back(GridPos{x, y});
                    }
                }
            }
        }
        if (cand.empty()) break;        // lattice full (cannot happen <= 20)
        GridPos p;
        const GridPos stem{0, 1};
        bool stemmed = false;
        if (step == 1) {
            // The start room always opens DOWNWARD (a stem) before the layout
            // fans out: the drawn layouts start with `S` above a single room,
            // and it also guarantees a VERTICAL room early on, which the
            // hazard roles (hot band, phase blink) need to exist at all.
            for (const GridPos& c : cand) {
                if (c.x == stem.x && c.y == stem.y) { p = c; stemmed = true; }
            }
        }
        if (!stemmed) {
            p = cand[LayoutMix((unsigned)level, (unsigned)step) % cand.size()];
        }
        used[p.y][p.x] = true;
        walk.push_back(p);
    }
    // Goal = the leaf (exactly one neighbour) farthest from the start.
    auto degree = [&](const GridPos& p) {
        int d = 0;
        if (p.x > 0 && used[p.y][p.x - 1]) ++d;
        if (p.x + 1 < kGridW && used[p.y][p.x + 1]) ++d;
        if (p.y > 0 && used[p.y - 1][p.x]) ++d;
        if (p.y + 1 < kGridH && used[p.y + 1][p.x]) ++d;
        return d;
    };
    auto dist = [&](const GridPos& p) {
        return std::abs(p.x) + std::abs(p.y);   // start is (0,0)
    };
    int best = -1;
    int bestD = -1;
    for (int i = 1; i < (int)walk.size(); ++i) {
        if (degree(walk[i]) != 1) continue;     // leaves only: the goal never
        const int d = dist(walk[i]);            // continues anywhere
        if (d > bestD) { bestD = d; best = i; }
    }
    if (best > 0) {
        std::swap(walk[best], walk.back());     // the goal room is the LAST room
    }
    return walk;
}

bool HasRoomAt(const std::vector<GridPos>& walk, int x, int y) {
    for (const GridPos& pos : walk) {
        if (pos.x == x && pos.y == y) {
            return true;
        }
    }
    return false;
}

// --- 2026-10-20: per-room ROLE (the HERO-style variety) ---------------------
// The generated stage used to be one shape with a bat; a level now alternates
// hazard rooms and normal rooms, and the last room can be a WATER goal
// (raft/tentacle + miner). Thresholds grow with the level number.
enum class Role { Normal, Hot, Gate, WaterGoal, Phase, Hcrunch };

struct LevelPlan {
    bool hot = false;       // hot row-1 bands
    bool gate = false;      // keyed gate room
    bool water = false;     // water goal (last room)
    bool tentacle = false;  // water goal hazard (otherwise a raft)
    bool extra = false;     // second enemy in normal rooms
    bool phase = false;     // blinking gate (timing room)
    bool hcrunch = false;   // horizontal crunch band (object-free room)
    bool patch = false;     // solid async block in normal rooms (a ledge)
    bool patch2 = false;    // a second block, opposite side (same room)
    bool twogap = false;    // two-gap vertical links (route choice)
};

LevelPlan PlanFor(int level) {
    LevelPlan p;
    p.hot = level >= 3;
    p.water = level >= 4;
    // Locked doors are DISABLED (user report 2026-10-21: level 13 could not
    // be completed). The door is an M1 column stripe, so it may only sit on a
    // column walled in bands 0/2 — i.e. NOT on a vertical corridor — and the
    // corridor is the only vertical passage. A true locked door needs
    // per-PAIR exit columns (a redesign); until then the gate role is played
    // by the blinking PHASE corridor, which does gate the corridor legally.
    p.gate = false;
    p.tentacle = level >= 7;
    p.extra = level >= 9;
    p.phase = level >= 6;       // timing gate on the corridor (was >= 11)
    p.hcrunch = level >= 14;    // crunch band sweeps the row-1 prefix
    p.patch = level >= 7;       // async block, now and then in normal rooms
    p.patch2 = level >= 12;     // two blocks (one per side) in that room
    // Exit-count variety (user rule 2026-10-21): from level 6 alternate the
    // vertical link scheme. A two-gap level has TWO separate exits at the top
    // and at the bottom (cells 3 and 6); a plain level has ONE wide exit
    // (cells 8-9). Same shape library, so the 6-bit shape index still fits.
    p.twogap = level >= 6 && level % 2 == 0;   // 6, 8, 10, ... 20
    return p;
}

std::vector<Role> HazardCycle(const LevelPlan& p) {
    std::vector<Role> h;
    if (p.hot) h.push_back(Role::Hot);
    if (p.gate) h.push_back(Role::Gate);
    if (p.phase) h.push_back(Role::Phase);
    if (p.hcrunch) h.push_back(Role::Hcrunch);
    return h;
}

Role RoleForRoom(int roomIndex, int roomCount, const LevelPlan& p) {
    if (roomIndex == roomCount - 1) {
        return p.water ? Role::WaterGoal : Role::Normal;
    }
    if (roomIndex == 0 || roomIndex % 2 == 0) {
        return Role::Normal;              // hazards alternate with breathers
    }
    const std::vector<Role> h = HazardCycle(p);
    if (h.empty()) return Role::Normal;
    return h[((roomIndex - 1) / 2) % h.size()];
}

// Exit mask a room's SHAPE must carry (see the layout notes above).
int RoomShapeMask(int levelNumber, const std::vector<GridPos>& walk,
                  const GridPos& pos, int roomIndex, Role role,
                  bool twogap) {
    int mask = 0;
    if (twogap) mask |= SHAPE_2GAP;
    if (HasRoomAt(walk, pos.x, pos.y - 1)) mask |= SHAPE_N;
    if (HasRoomAt(walk, pos.x, pos.y + 1)) mask |= SHAPE_S;
    // Link `i` joins walk[i] -> walk[i+1]; a room's TOP uses link i-1 and its
    // BOTTOM uses link i, so alternating the width per link makes every
    // through-room's top/bottom differ (user rule 2026-10-21).
    if (levelNumber >= 6) {
        if ((mask & SHAPE_N) && (roomIndex - 1) % 2 == 0) mask |= SHAPE_N1;
        if ((mask & SHAPE_S) && roomIndex % 2 == 0) mask |= SHAPE_S1;
    }
    // Side openings come from ADJACENCY (user rule 2026-10-24). ONE bit covers
    // both sides: the playfield is reflected, cell 0 is drawn on both edges, so
    // a room with a single horizontal neighbour also shows a dead aperture on
    // its far side (the exit scan finds no room there and the player stops at
    // the edge — it cannot tear a transition).
    if (HasRoomAt(walk, pos.x - 1, pos.y)
            || HasRoomAt(walk, pos.x + 1, pos.y)) {
        mask |= SHAPE_H;
    }
    if (roomIndex == 0) mask |= SHAPE_START;   // the level's spawn room
    if (IsChannelRoom(levelNumber, walk, pos)) {
        mask |= SHAPE_CHANNEL;
    } else {
        if (role == Role::Gate || role == Role::Phase) mask |= SHAPE_GATE;
        if (role == Role::WaterGoal) mask |= SHAPE_WATER;
    }
    return mask;
}

int Lift(int value) {                 // a lighter wall colour for the row-1 band
    return value + 40 > 255 ? 255 : value + 40;
}

// One room's objects. The editor's caps are the contract: <= 2 objects per
// room (enemies + lamps + miner) and <= 1 element per tile row (MapCanvas
// kMaxRoomElements / ElementInRow, verify_build repeats the 2-object cap).
// Row = y/4 (rows 0/1/2), the same conversion convert uses.
void AddEnemy(RoomData& room, EnemyType type, float x, float y, float speed,
              float rangeMax, int dir = 1) {
    EnemyData e;
    e.type = (int)type;
    e.x = x;
    e.y = y;
    e.range_min = 0.0f;
    e.range_max = rangeMax;
    e.speed = speed;
    e.dir = dir;
    room.enemies.push_back(e);
}

int RowOf(float y) { return (int)y / 4; }

bool RowOccupied(const RoomData& room, int row) {
    for (const EnemyData& e : room.enemies) {
        if (RowOf(e.y) == row) return true;
    }
    for (const LampData& l : room.lamps) {
        if (RowOf(l.y) == row) return true;
    }
    return false;
}

int ObjectCount(const RoomData& room) {
    return (int)(room.enemies.size() + room.lamps.size());
}

// ---- placement primitives (user rules 2026-10-21) -------------------------
// A shape's tiles: 0 = air, non-zero = wall (a hot row-1 wall is still solid).
// Enemies and lamps must never sit inside a wall — the SNAKE is the documented
// exception (it lives in the wall and needs open air on the side it faces).
bool CellAir(const ModelData& m, int band, int cell) {
    return cell >= 0 && cell < kRoomWidth
        && m.tiles[band * kRoomWidth + cell] == 0;
}

// Nearest AIR cell of `band` to `prefer` (search outward), or -1 if the band is
// fully solid.
int NearestAir(const ModelData& m, int band, int prefer) {
    if (prefer < 0) prefer = 0;
    if (prefer >= kRoomWidth) prefer = kRoomWidth - 1;
    if (CellAir(m, band, prefer)) return prefer;
    for (int d = 1; d < kRoomWidth; ++d) {
        if (CellAir(m, band, prefer - d)) return prefer - d;
        if (CellAir(m, band, prefer + d)) return prefer + d;
    }
    return -1;
}

// N=4 (2026-10-24): the PLANS speak three rows (0 ceiling / 1 shaft / 2 floor)
// but a generated model carries one row per drawn band, band 2 being the
// vertical route's continuation. Placement code that means "the floor / water
// row" must ask for this band, never use the literal 2 (a literal 2 now lands
// in the route shaft, where the cell is usually a wall).
int FloorBand(const ModelData& m) { return m.height > 3 ? m.height - 1 : 2; }
// Object y lives in DISPLAY ROW units of 12 px over the 144-px cave, so a band
// spans 12/height units (4 for a 3-row model, 3 for a 4-row one).
int BandUnits(const ModelData& m) { return m.height > 0 ? 12 / m.height : 4; }
float BandY(const ModelData& m, int band) {
    const int u = BandUnits(m);
    return (float)(band * u + (band == 0 ? 1 : u / 2));
}

// A lamp hangs in a GAP, on the side next to a wall (user rule 2026-10-21):
// an air cell whose left or right neighbour is a REAL wall. The screen edge
// and the reflected centre seam are open space, not walls, so the test is
// explicit about the cell range (a lamp at cell 9 against the mirror is
// floating — user report: "between the tiles"). Returns cell or -1.
int LampCell(const ModelData& m, int band, int prefer) {
    if (prefer < 0) prefer = 0;
    if (prefer >= kRoomWidth) prefer = kRoomWidth - 1;
    auto wallAt = [&](int c) {
        return c >= 0 && c < kRoomWidth && !CellAir(m, band, c);
    };
    for (int d = 0; d < kRoomWidth; ++d) {
        for (int s = 0; s < 2; ++s) {
            const int c = prefer + (s ? d : -d);
            if (!CellAir(m, band, c)) continue;
            if (wallAt(c - 1) || wallAt(c + 1)) return c;
        }
    }
    return -1;
}

// --- completability guard (user 2026-10-21) --------------------------------
// A generated room must let the player THROUGH: every way in (top edge, and
// the row-1 cell 0 horizontal edge) must reach a way out (bottom edge / the
// horizontal edge) through air. PF walls span the full 48-line band, so a
// band-1 wall that misses the vertical corridor seals the room — exactly the
// family that soft-locked level 13. Phase/hcrunch cells are gated at run time
// and therefore count as passable; a LOCKED door never sits on the generator's
// models (the door is a room patch).
// Returns an empty string when the room is fine, else a short description.
std::string RoomConnectivityProblem(const ModelData& m) {
    auto air = [&](int band, int x) { return CellAir(m, band, x); };
    // Height-aware (N=4): the south edge is the LAST band and the pads add a
    // band in the middle, so a generated 4-row model is checked as it ships.
    const int bands = (m.width > 0)
        ? (int)m.tiles.size() / m.width : 0;
    if (bands < 3) return "";
    const int last = bands - 1;
    std::vector<std::pair<int, int>> ins, outs;
    for (int x = 0; x < kRoomWidth; ++x) {
        if (air(0, x)) ins.push_back({0, x});
        if (air(last, x)) outs.push_back({last, x});
    }
    if (air(1, 0)) {
        ins.push_back({1, 0});
        outs.push_back({1, 0});
    }
    if (ins.empty() || outs.empty()) return "";   // sentinel / dead end
    for (const auto& start : ins) {
        bool seen[8][hero::kRoomWidth] = {};
        std::vector<std::pair<int, int>> stack{start};
        seen[start.first][start.second] = true;
        while (!stack.empty()) {
            auto [y, x] = stack.back();
            stack.pop_back();
            static const int dy[4] = {1, -1, 0, 0};
            static const int dx[4] = {0, 0, 1, -1};
            for (int k = 0; k < 4; ++k) {
                const int ny = y + dy[k], nx = x + dx[k];
                if (ny < 0 || ny >= bands || nx < 0
                        || nx >= kRoomWidth) continue;
                if (seen[ny][nx] || !CellAir(m, ny, nx)) continue;
                seen[ny][nx] = true;
                stack.push_back({ny, nx});
            }
        }
        bool reaches = false;
        for (const auto& goal : outs) {
            if (seen[goal.first][goal.second]) { reaches = true; break; }
        }
        if (!reaches) {
            return "entry cell (" + std::to_string(start.first) + ","
                 + std::to_string(start.second) + ") reaches no exit";
        }
    }
    return "";
}

void FillRoomObjects(int levelNumber, int roomIndex, int roomCount, Role role,
                     const LevelPlan& plan, RoomData& room,
                     const ModelData& shape,
                     bool roomIsKeyHost = false, int arch = 0) {
    if (roomIndex == roomCount - 1) {
        if (role == Role::WaterGoal) {
            // Water goal: the miner waits above the water; the raft ferries
            // (early levels) or a tentacle guards the surface (level 7+).
            room.bottom_band = true;
            room.bottom_r = 24;
            room.bottom_g = 88;
            room.bottom_b = 208;
            if (plan.tentacle) {
                // On open water: the row may carry the miner rock / two-gap
                // walls, so snap to the nearest air cell (the water band).
                const int tcell = NearestAir(shape, FloorBand(shape), 5);
                if (tcell >= 0) {
                    AddEnemy(room, EnemyType::TENTACLE, (float)(tcell * 2),
                             BandY(shape, FloorBand(shape)), 1.0f, 0.0f);
                }
            } else {
                // Off the miner's rock (cells 2..3): ferry lane at cell 6.
                AddEnemy(room, EnemyType::RAFT, 12.0f,
                         BandY(shape, FloorBand(shape)), 1.0f, 0.0f);
            }
        } else if (roomCount > 1 && levelNumber >= 2) {
            // Goal room: the miner sits at x=4, so an enemy past it (the old
            // wall snake at cell 0) was never fought (user rule 2026-10-21).
            // From level 2 one bat guards the APPROACH corridor (cell 8),
            // which also keeps the 2-room levels distinct (L1 is clean).
            const int cell = NearestAir(shape, 1, 8);
            if (cell >= 0) {
                AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                         (levelNumber % 2) ? 4.0f : 5.0f,
                         1.25f + 0.25f * (levelNumber % 4), 13.0f);
            }
        }
        return;
    }
    if (roomIndex == 0) {
        // Start room: NO enemies (user rule 2026-10-21) — the player spawns
        // here and an enemy behind spawn is never met. Hot walls are allowed
        // on advanced levels (see the archetype pick in Build20LevelStage),
        // and async blocks sit near the exit gap.
        return;
    }
    if (role == Role::Gate || role == Role::Phase) {
        // Door rooms allow ONE non-key enemy (convert rule). The gap itself is
        // a LOCKED_DOOR / PHASE cell — a bat there is inside the door half the
        // time — so it guards the descent ABOVE the gap (band 0), on the
        // nearest open cell (user rule 2026-10-21: no enemy inside a wall).
        const int cell = NearestAir(shape, 0, 4);
        if (cell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                     BandY(shape, 0),
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
        return;
    }
    if (role == Role::Hcrunch) {
        // Convert rule: an hcrunch room has NO objects (the band owns the
        // sprite slot), so this room is empty on purpose.
        return;
    }
    if (role == Role::Hot) {
        // HOT rooms: NO middle-band objects (user rule 2026-10-21) — the
        // other two bands may each carry one. The gap archetypes block the
        // CENTRE (row 1), so the guards go on the OPEN cells of bands 0/2
        // near that gap — never inside the band-0/2 walls (user report
        // 2026-10-21: a bat inside the wall at level 3 room 2).
        const int hidx = (arch >= 8 && arch <= 14) ? arch - 8 : 0;
        const int gapCell = kArchHotGapX[hidx] / 2;
        const int bcell = NearestAir(shape, 0, gapCell);
        if (bcell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(bcell * 2),
                     BandY(shape, 0),
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
        if (levelNumber >= 5) {
            const int scell = NearestAir(shape, FloorBand(shape),
                                         gapCell == 3 ? 6 : 3);
            if (scell >= 0) {
                AddEnemy(room, EnemyType::SPIDER, (float)(scell * 2),
                         BandY(shape, FloorBand(shape)),
                         1.0f + 0.25f * (levelNumber % 4), 8.0f);
            }
        }
        return;
    }
    // Normal room: bat/lamp. A LAMP only matters where the dark mask reaches
    // (rooms 0-7), so deeper rooms get a bat.
    // Normal rooms: one object in the middle band (the shaft, cell 8) and, from
    // level 5, a second on ANOTHER band (top corridor, cell 8) — 2 objects per
    // room, one per band, as the user asked (2026-10-21). Flicker is the
    // kernel's job (one sprite), not a reason to starve the rooms.
    if (roomIndex % 2 == 1 || roomIndex >= 8) {
        const int cell = NearestAir(shape, 1, 8);
        if (cell >= 0) {
            AddEnemy(room, EnemyType::BAT, (float)(cell * 2),
                     (levelNumber % 2) ? 4.0f : 5.0f,
                     1.25f + 0.25f * (levelNumber % 4), 13.0f);
        }
    } else {
        // A lamp hangs in a gap next to a wall (user rule 2026-10-21): a lamp
        // floating in open air reads as "between the tiles" (level 4 room 3).
        // The lamp must hang in a gap NEXT TO A WALL (user rule 2026-10-21):
        // a lamp floating in the open reads as "between the tiles". The maze
        // layout has rooms whose band 1 is one wide aisle, so if no legal cell
        // exists in band 1 try band 0 and otherwise SKIP the lamp — the old
        // NearestAir fallback put it in the open.
        int cell = LampCell(shape, 1, 8);
        int lampBand = 1;
        if (cell < 0) {
            cell = LampCell(shape, 0, 8);
            lampBand = 0;
        }
        if (cell >= 0) {
            LampData lamp;
            lamp.x = (float)(cell * 2);
            lamp.y = BandY(shape, lampBand);
            lamp.lit = true;
            room.lamps.push_back(lamp);
        }
    }
    // From level 5 a second object on another band. Skip the room right
    // before a gate: it is the key host (the key needs a free slot, and a key
    // in the START room would break the clean-spawn rule).
    //
    // Pick the first band that ACTUALLY has air (2026-10-24): the maze shapes
    // have solid ceilings/ledges, so "row 0 is free" no longer implies an air
    // cell there — the old if/else chain then placed nothing at all.
    if (levelNumber >= 5 && !roomIsKeyHost) {
        for (const int band : {0, FloorBand(shape), 2}) {
            if (RowOccupied(room, band)) continue;
            const int cell = NearestAir(shape, band, 8);
            if (cell < 0) continue;
            AddEnemy(room, EnemyType::SPIDER, (float)(cell * 2),
                     BandY(shape, band),
                     1.0f + 0.25f * (levelNumber % 4), 8.0f);
            break;
        }
    }
}

}  // namespace

// Stage-level LINK check (user rule 2026-10-24). See the header for the rule:
// the runtime exit fires when the player reaches the screen edge and never
// tests the neighbour's wall, so a half-carved link or a band mismatch drops
// him inside a wall on the room change. This mirrors
// tools/convert_level.check_stage_connections (the build gate).
std::vector<std::string> DataSerializer::StageConnectionProblems(
        const std::vector<LevelData>& levels,
        const std::vector<ModelData>& models) {
    std::vector<std::string> out;
    auto findModel = [&](int id) -> const ModelData* {
        for (const auto& m : models) {
            if (m.id == id) return &m;
        }
        return nullptr;
    };
    auto sideBands = [](const ModelData& m) {
        std::vector<int> v;
        for (int band = 1; band <= 2; ++band) {
            if (CellAir(m, band, 0)) v.push_back(band);
        }
        return v;
    };
    int level_n = 0;
    for (const auto& level : levels) {
        ++level_n;
        auto findRoom = [&](int x, int y) -> const RoomData* {
            for (const auto& r : level.rooms) {
                if (r.room_x == x && r.room_y == y) return &r;
            }
            return nullptr;
        };
        for (const auto& room : level.rooms) {
            const ModelData* a = findModel(room.model_id);
            if (!a || a->width <= 0) continue;
            const int bands = (int)a->tiles.size() / a->width;
            if (bands < 3) continue;
            if (const RoomData* east = findRoom(room.room_x + 1, room.room_y)) {
                const ModelData* b = findModel(east->model_id);
                if (!b) continue;
                const std::vector<int> sa = sideBands(*a), sb = sideBands(*b);
                bool shared = false;
                for (int x : sa) {
                    for (int y : sb) {
                        if (x == y) shared = true;
                    }
                }
                if (!sa.empty() && !sb.empty() && !shared) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " and "
                        + std::to_string(east->room_id)
                        + " are side by side but open in different bands "
                        "(landing inside a wall)");
                } else if (sa.empty() != sb.empty()) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " and "
                        + std::to_string(east->room_id)
                        + " are side by side but only one has a side opening");
                }
            }
            if (const RoomData* south = findRoom(room.room_x, room.room_y + 1)) {
                const ModelData* b = findModel(south->model_id);
                if (!b || b->width <= 0) continue;
                if ((int)b->tiles.size() / b->width < 1) continue;
                bool shared = false, any = false;
                for (int x = 0; x < kRoomWidth; ++x) {
                    const bool up = CellAir(*a, bands - 1, x);
                    const bool dn = CellAir(*b, 0, x);
                    any = any || up || dn;
                    shared = shared || (up && dn);
                }
                if (any && !shared) {
                    out.push_back(
                        "level " + std::to_string(level_n) + ": rooms "
                        + std::to_string(room.room_id) + " (above) and "
                        + std::to_string(south->room_id)
                        + " (below) share no open column (landing inside a "
                        "wall)");
                }
            }
        }
    }
    return out;
}


void DataSerializer::Build20LevelStage(std::vector<LevelData>& levels,
                                       std::vector<ModelData>& models) {
    // 1. Every level's walk + the shape mask of each of its rooms. A room's
    //    ROLE (hot / gate / water goal) is part of the shape, so the library
    //    carries hazard variants as well as exit masks. Two passes: the base
    //    library first; if it fits under kShapeBudget the EXTRA archetype
    //    variants are enabled (the generator spends real headroom, never
    //    guesses).
    std::vector<std::vector<GridPos>> walks(kStageLevels);
    std::vector<std::vector<int>> masks(kStageLevels);
    std::vector<std::vector<Role>> roles(kStageLevels);
    std::set<int> used;
    // `variety` = how many ARCHETYPES each room type may use. With the maze
    // layout the exit combinations multiply (7 combos x 2Gap x role bits), so
    // the archetype count is the budget knob: fixed pools wanted 103 shapes,
    // over the 64 the 6-bit shape index allows (measured 2026-10-24).
    auto buildLibrary = [&](bool withExtras, int variety) {
        used.clear();
        for (int l = 1; l <= kStageLevels; ++l) {
            walks[l - 1] = LevelLayout(l, l < 2 ? 2 : l);
            const LevelPlan plan = PlanFor(l);
            const int count = (int)walks[l - 1].size();
            masks[l - 1].clear();
            roles[l - 1].clear();
            // Pass 1: the roles. A hazard needs a room that can HOST it: the
            // maze decides which rooms have a vertical passage, and the three
            // vertical hazards (hot band, phase blink, crunch sweep) need one
            // — a crunch room also cannot host a side link (its band 1 is one
            // solid feature prefix). When the chosen room cannot host, the
            // role MOVES to the first free room that can (user rule 2026-10-24:
            // the layout decides the shapes, so the hazard follows the layout).
            std::vector<bool> vroom(count, false), hroom(count, false);
            std::vector<Role> rl(count, Role::Normal);
            for (int i = 0; i < count; ++i) {
                const GridPos& p = walks[l - 1][i];
                vroom[i] = HasRoomAt(walks[l - 1], p.x, p.y - 1)
                        || HasRoomAt(walks[l - 1], p.x, p.y + 1);
                hroom[i] = HasRoomAt(walks[l - 1], p.x - 1, p.y)
                        || HasRoomAt(walks[l - 1], p.x + 1, p.y);
                rl[i] = RoleForRoom(i, count, plan);
                if (IsChannelRoom(l, walks[l - 1], p)) rl[i] = Role::Normal;
            }
            auto canHost = [&](int i, Role r) {
                if (i <= 0 || i >= count - 1) return false;
                if (r == Role::Hot || r == Role::Phase) return (bool)vroom[i];
                // Since 2026-10-24 the kernel prefix starts at pair 1, so a
                // crunch room keeps its side link (the crush gates the way out of
                // the 8-px edge vestibule); it still needs a vertical passage.
                if (r == Role::Hcrunch) return (bool)vroom[i];
                return true;
            };
            // Most RESTRICTIVE first: the crunch needs a vertical-only room
            // (its band 1 is one solid feature prefix, so it cannot host a
            // side link), while hot/phase only need a vertical one. On a dense
            // level the stem room is usually the only vertical-only room, so
            // the crunch claims it and hot moves elsewhere.
            for (const Role want : {Role::Hcrunch, Role::Hot, Role::Phase}) {
                for (int i = 1; i < count - 1; ++i) {
                    if (rl[i] != want || canHost(i, want)) continue;
                    int host = -1;
                    for (int j = 1; j < count - 1 && host < 0; ++j) {
                        if (j != i && rl[j] == Role::Normal && canHost(j, want)) {
                            host = j;
                        }
                    }
                    if (host < 0) {
                        // No free host: STEAL one from a less restrictive role
                        // (hot/phase) that has somewhere else to go.
                        for (int j = 1; j < count - 1 && host < 0; ++j) {
                            if (j == i || !canHost(j, want)) continue;
                            if (rl[j] == Role::Normal) {
                                host = j;
                                break;
                            }
                            if (rl[j] != Role::Hot && rl[j] != Role::Phase) {
                                continue;
                            }
                            bool moved = false;
                            for (int k = 1; k < count - 1; ++k) {
                                if (k == i || k == j) continue;
                                if (rl[k] == Role::Normal && canHost(k, rl[j])) {
                                    rl[k] = rl[j];
                                    moved = true;
                                    break;
                                }
                            }
                            // The crunch is the rarest hazard (it needs a
                            // vertical-only room): if the victim cannot be
                            // rehoused, it is dropped and the crunch takes the
                            // host anyway.
                            rl[j] = Role::Normal;
                            host = j;
                            (void)moved;
                        }
                    }
                    if (host < 0) {
                        rl[i] = Role::Normal;   // nowhere to host it: drop it
                        continue;
                    }
                    rl[i] = Role::Normal;
                    rl[host] = want;
                }
            }
            // Pass 2: the shape mask (arch keyed by the room's role + the exit
            // combination; corridor rooms stay plain, see below).
            for (int i = 0; i < count; ++i) {
                const Role role = rl[i];
                roles[l - 1].push_back(role);
                const GridPos& here = walks[l - 1][i];
                const bool verticalRoom = vroom[i];
                int arch = 0;
                if (verticalRoom
                        && !IsChannelRoom(l, walks[l - 1], here)) {
                    if (role == Role::Hot) {
                        const int* pool;
                        int n;
                        if (l > 10) {
                            pool = withExtras ? kHotExtra : kHotLate;
                            n = withExtras ? 6 : 4;
                        } else {
                            pool = kHotBase;
                            n = 3;
                        }
                        if (n > variety) n = variety;
                        arch = pool[l % n];
                    } else if (i == 0 && l >= 8) {
                        // The START room drops the player in at cell 4, so its
                        // band 1 MUST keep that column open: arch 14 is
                        // HotDrop, the only start archetype with the drop
                        // column carved.
                        arch = 14;
                    } else if (role == Role::Normal && i > 0
                               && i < count - 1) {
                        const int* pool = withExtras ? kNormalExtra
                                                     : kNormalBase;
                        int n = withExtras ? 7 : 5;
                        if (n > variety) n = variety;
                        arch = pool[(l + i) % n];
                    }
                }
                const int mask = RoomShapeMask(l, walks[l - 1], walks[l - 1][i],
                                               i, role, plan.twogap)
                                 | (arch << kArchShift);
                masks[l - 1].push_back(mask);
                used.insert(mask);
            }
        }
    };
    // Widest archetype set that fits the budget, then the richer archetypes
    // if they also fit; otherwise keep the base library.
    for (int variety = 3; variety >= 1; --variety) {
        buildLibrary(false, variety);
        if ((int)used.size() <= kShapeBudget) break;
    }
    {
        const std::vector<std::vector<int>> baseMasks = masks;
        const std::vector<std::vector<Role>> baseRoles = roles;
        const std::set<int> baseUsed = used;
        buildLibrary(true, 3);
        if ((int)used.size() > kShapeBudget || (int)used.size() > 64) {
            masks = baseMasks;
            roles = baseRoles;
            used = baseUsed;
        }
    }

    // 2. The shape library: model ids ARE the ascending masks (deterministic).
    models.clear();
    std::map<int, int> shapeId;
    for (int mask : used) {
        shapeId[mask] = (int)models.size();
        models.push_back(MakeShapeModel(shapeId[mask], mask));
    }

    // 3. The levels, in play order.
    levels.clear();
    levels.reserve(kStageLevels);
    // COMPLETABILITY GUARD: refuse to emit a stage whose rooms cannot be
    // crossed (construction opens the corridor, but a future edit could break
    // it; the editor and the CLI both surface this as a hard error).
    for (const ModelData& m : models) {
        const std::string problem = RoomConnectivityProblem(m);
        if (!problem.empty()) {
            throw std::runtime_error("generated room '" + m.name + "' is "
                                     "impassable: " + problem);
        }
    }

    for (int l = 1; l <= kStageLevels; ++l) {
        LevelData level;
        level.level_id = l;
        level.name = "Level " + std::to_string(l);
        level.wall_r = kLevelPalettes[l - 1][0];
        level.wall_g = kLevelPalettes[l - 1][1];
        level.wall_b = kLevelPalettes[l - 1][2];
        level.wall2_r = Lift(level.wall_r);
        level.wall2_g = Lift(level.wall_g);
        level.wall2_b = Lift(level.wall_b);
        level.start_room = 0;                 // convert: 0 is the kernel constant
        const int roomCount = (int)walks[l - 1].size();
        level.miner_room = roomCount - 1;     // the goal is the last room
        level.miner_x = kMinerX;              // on the water-goal rock
        // User rule 2026-10-21: if the walk enters the goal room from a SIDE,
        // the miner waits on the OPPOSITE side (on the entry side the room is
        // trivial). Vertical entry keeps the left-positioned miner.
        if (roomCount >= 2) {
            const GridPos& goalPos = walks[l - 1][roomCount - 1];
            const GridPos& prevPos = walks[l - 1][roomCount - 2];
            if (prevPos.x != goalPos.x) {
                level.miner_x = (prevPos.x < goalPos.x) ? kMinerFarX
                                                        : kMinerX;
            }
        }
        // Miner Y = the goal rock top - 12 px: 84 px (7 rows) on a 3-band room,
        // 96 px (8 rows) on a 4-band one (the floor band sits 36 px lower).
        // Every water-goal shape is a non-gate shape, so it is 4-row.
        level.miner_y = 8.0f;
        level.miner_dir = 1;
        const LevelPlan plan = PlanFor(l);
        for (int i = 0; i < roomCount; ++i) {
            RoomData room;
            room.room_id = i;
            room.model_id = shapeId[masks[l - 1][i]];
            room.room_x = walks[l - 1][i].x;
            room.room_y = walks[l - 1][i].y;
            if (roles[l - 1][i] == Role::Gate) {
                // LOCKED_DOOR cells ON THE CORRIDOR (left/M1 side), one per
                // corridor cell (2 max = the patch cap). Solid until the
                // level's key is held, then touch opens the room's door.
                const int doorCol = (masks[l - 1][i] & SHAPE_2GAP)
                                        ? kGapA : kVertExitA;
                room.asym_patches.push_back(
                    {1, doorCol, (int)TileType::LOCKED_DOOR, 1});
            }
            if (roles[l - 1][i] == Role::Phase) {
                // The corridor blinks: 45 frames solid, 45 open. Both
                // corridor cells so the blink gates the whole passage.
                // The phase sits on the room's PASSAGE cell: a gate shape
                // keeps band 1 open at the first corridor cell only.
                room.feature_cells.push_back(
                    {1, (masks[l - 1][i] & SHAPE_2GAP) ? kGapA : kVertExitA,
                     (int)TileType::PHASE});
            }
            if (roles[l - 1][i] == Role::Hcrunch) {
                // Fixed 10-cell prefix on the middle band (live stage form).
                for (int c = 0; c < kRoomWidth; ++c) {
                    room.feature_cells.push_back(
                        {1, c, (int)TileType::HCRUNCH});
                }
            }
            // Advanced hot rooms (> level 10): a solid async block sits in
            // the gap the player must use — bomb it (thin cell) or take the
            // longer gap (usefull_hot_walls_004). The M1 column needs walls
            // in bands 0/2, so scan for a legal cell near the gap.
            // Start rooms never take a hot gap block: their drop column must
            // stay open (HotDrop), and they carry their own async rule below.
            if (roles[l - 1][i] == Role::Hot && l > 10 && i != 0) {
                const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                const int hidx = ((masks[l - 1][i] >> kArchShift) & kArchMask) - 8;
                const int gapCell = kArchHotGapX[hidx] / 2;
                for (int c = gapCell; c <= gapCell + 1; ++c) {
                    if (c < 1 || c > 7) continue;
                    if (sm.tiles[1 * kRoomWidth + c] == 0
                            && sm.tiles[0 * kRoomWidth + c] != 0
                            && sm.tiles[2 * kRoomWidth + c] != 0
                            && (sm.height <= 3
                                || sm.tiles[3 * kRoomWidth + c] != 0)) {
                        room.asym_patches.push_back(
                            {1, c, (int)TileType::SOLID_WALL, 1});
                        break;
                    }
                }
            }
            // Start room: an async block beside the exit gap from level 7
            // (user rule 2026-10-21: first room has no enemies, but async in
            // the path is welcome). Cell 7 + its mirror cell 2 are open in
            // every start shape (row 1 is '#.........').
            if (i == 0 && plan.patch && l >= 7) {
                // M1 guard: the patch cell must be OPEN in band 1 and WALLED in
                // bands 0/2 (the whole-cave strip paints/hides the column).
                // Prefer col 7 (next to the exit gap); hot archetypes may fill
                // it, so fall back to 1.
                const ModelData& sm0 = models[shapeId[masks[l - 1][i]]];
                for (int c : {7, 6, 5, 4, 3, 2, 1}) {
                    if (sm0.tiles[1 * kRoomWidth + c] == 0
                            && sm0.tiles[0 * kRoomWidth + c] != 0
                            && sm0.tiles[2 * kRoomWidth + c] != 0
                            && (sm0.height <= 3
                                || sm0.tiles[3 * kRoomWidth + c] != 0)) {
                        room.asym_patches.push_back(
                            {1, c, (int)TileType::SOLID_WALL, 1});
                        break;
                    }
                }
            }
            // Async BLOCKS: a plain solid patch (not a special) sprinkled
            // through ordinary rooms so async rides WITH enemies. The gate/
            // phase/hcrunch rooms keep their own special alone; the start and
            // goal rooms stay clean (spawn/pickup).
            //
            // M1 (side 1) is the primary: the whole-cave latch needs the
            // patched band OPEN and the other two bands WALLED at that column.
            // The optional second block is the BALL (side 0, additive) on the
            // mirrored cell — it only needs band 1 open there.
            if (roles[l - 1][i] == Role::Normal && i > 0
                    && i < roomCount - 1 && plan.patch && i % 3 == 2) {
                const ModelData& sm = models[shapeId[masks[l - 1][i]]];
                int col = -1;
                for (int c = 1; c <= 7; ++c) {
                    // The M1 strip paints ONE column across the WHOLE cave, so
                    // every band the patch does not paint must be walled there
                    // — band 3 included now that the floor is its own band
                    // (2026-10-24; the converter hard-fails otherwise).
                    if (sm.tiles[1 * kRoomWidth + c] == 0
                            && sm.tiles[0 * kRoomWidth + c] != 0
                            && sm.tiles[2 * kRoomWidth + c] != 0
                            && (sm.height <= 3
                                || sm.tiles[3 * kRoomWidth + c] != 0)) {
                        col = c;
                        break;
                    }
                }
                if (col >= 0) {
                    room.asym_patches.push_back(
                        {1, col, (int)TileType::SOLID_WALL, 1});
                    if (plan.patch2) {
                        const int other = kRoomWidth - 1 - col;
                        if (sm.tiles[1 * kRoomWidth + other] == 0) {
                            room.asym_patches.push_back(
                                {1, other, (int)TileType::SOLID_WALL, 0});
                        }
                    }
                }
            }
            if (masks[l - 1][i] & SHAPE_CHANNEL) {
                // Water crossing: raft on the open water + one bat in the
                // centre shaft (cell 8). No role objects (the hot ceiling is
                // the challenge).
                room.bottom_band = true;
                room.bottom_r = 24;
                room.bottom_g = 88;
                room.bottom_b = 208;
                AddEnemy(room, EnemyType::RAFT, 4.0f,
                         BandY(models[shapeId[masks[l - 1][i]]],
                              FloorBand(models[shapeId[masks[l - 1][i]]])),
                         1.0f, 0.0f);
                const int chBat = NearestAir(models[shapeId[masks[l - 1][i]]],
                                             0, 8);
                if (chBat >= 0) {
                    AddEnemy(room, EnemyType::BAT, (float)(chBat * 2),
                         BandY(models[shapeId[masks[l - 1][i]]], 0),
                             1.25f + 0.25f * (l % 4), 13.0f);
                }
            } else {
                const bool keyHost = (i + 1 < roomCount
                                      && roles[l - 1][i + 1] == Role::Gate);
                const int roomArch = (masks[l - 1][i] >> kArchShift) & kArchMask;
                const ModelData& roomShape = models[shapeId[masks[l - 1][i]]];
                FillRoomObjects(l, i, roomCount, roles[l - 1][i], plan, room,
                                roomShape, keyHost, roomArch);
            }
            level.rooms.push_back(room);
        }
        // Keys: one per gate, placed in the nearest earlier room that is not
        // another gate and has a free row (row 2 first). Row = y/4.
        for (int i = 1; i < roomCount; ++i) {
            if (roles[l - 1][i] != Role::Gate) continue;
            // Host search: PREFER middle rooms (the start room is the clean
            // spawn — no enemies/items unless there is no other host).
            bool keyPlaced = false;
            for (int j = i - 1; j >= 1 && !keyPlaced; --j) {
                if (roles[l - 1][j] == Role::Gate) continue;
                if (roles[l - 1][j] == Role::Hcrunch) continue;  // no objects
                if (ObjectCount(level.rooms[j]) >= 2) continue;
                // Free cells the shape actually has open: row 1 cell 5 (x 10)
                // on normal/hot shapes, else the exit corridor (cell 8, x 16).
                const ModelData& kShape = models[shapeId[masks[l - 1][j]]];
                int kband = 1, kprefer = 5;
                float ky = 5.0f;
                if (RowOccupied(level.rooms[j], 1)) {
                    if (!RowOccupied(level.rooms[j], 0)) {
                        kband = 0; kprefer = 8; ky = BandY(kShape, 0);
                    } else if (!RowOccupied(level.rooms[j],
                                            FloorBand(kShape))) {
                        kband = FloorBand(kShape); kprefer = 8;
                        ky = BandY(kShape, kband);
                    } else {
                        continue;
                    }
                }
                const int kcell = NearestAir(kShape, kband, kprefer);
                if (kcell < 0) continue;
                AddEnemy(level.rooms[j], EnemyType::KEY, (float)(kcell * 2),
                         ky, 1.0f, 0.0f);
                keyPlaced = true;
            }
            if (!keyPlaced && ObjectCount(level.rooms[0]) < 2
                    && !RowOccupied(level.rooms[0], 1)) {
                const int kcell = NearestAir(
                    models[shapeId[masks[l - 1][0]]], 1, 5);
                if (kcell >= 0) {
                    AddEnemy(level.rooms[0], EnemyType::KEY,
                             (float)(kcell * 2), 5.0f, 1.0f, 0.0f);
                }
            }
        }
        // Two-gap route choice (user rule 2026-10-20): one of the two
        // ceiling gaps carries a lamp (even rooms) or a spider (odd rooms),
        // the other stays empty — dropping blind is the risk. Runs AFTER the
        // keys so a gate's host room keeps its free slot; gate/hcrunch rooms
        // are skipped (door rule / no objects).
        if (plan.twogap) {
            for (int i = 1; i < roomCount - 1; ++i) {
                if (roles[l - 1][i] == Role::Hcrunch
                        || roles[l - 1][i] == Role::Gate) continue;
                RoomData& room = level.rooms[i];
                if (ObjectCount(room) >= 2 || RowOccupied(room, 0)) continue;
                const int gap = (i % 2) ? kGapB : kGapA;
                const ModelData& gShape = models[shapeId[masks[l - 1][i]]];
                if (i % 2 || i >= 8) {   // lamps only where the dark mask works
                    const int gcell = NearestAir(gShape, 0, gap);
                    if (gcell < 0) continue;
                    AddEnemy(room, EnemyType::SPIDER, (float)(gcell * 2),
                             BandY(gShape, 0), 1.0f + 0.25f * (l % 4),
                             8.0f);
                } else {
                    const int gcell = LampCell(gShape, 0, gap);
                    if (gcell < 0) continue;
                    LampData lamp;
                    lamp.x = (float)(gcell * 2);
                    lamp.y = BandY(gShape, 0);
                    lamp.lit = true;
                    room.lamps.push_back(lamp);
                }
            }
        }
        levels.push_back(level);
    }

    // N=4 (2026-10-24): the PLANS are built in 3 rows (0 ceiling / 1 shaft /
    // 2 floor) and MakeShapeModel emits 4 bands, band 2 being the vertical
    // route's continuation. Gate/phase shapes stay 3-row (their door cell IS
    // the corridor, so band 2 has to stay open for the descent and the strip
    // cannot be patched twice) and the converter/editor pad those on load.

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
