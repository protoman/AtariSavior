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
#include <sstream>
#include <iterator>

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
constexpr int kColumnRooms = 10;     // rooms per serpentine column (< span 15)
constexpr int kTurnY = kColumnRooms - 1;
// Exit bits + hazard bits (2026-10-20: the generated stage got its HERO-style
// variety — hot bands, a keyed gate, water goals with raft/tentacle).
enum ShapeBits {
    SHAPE_N = 1,
    SHAPE_S = 2,
    SHAPE_H = 4,
    SHAPE_START = 8,
    SHAPE_HOT = 16,      // row-1 walls hot (model mid_band_type = 1)
    SHAPE_GATE = 32,     // row-1 wall with ONE open gap (door / gate column)
    SHAPE_WATER = 64     // row-2 open water (bottom band, raft/tentacle)
};
constexpr int kGateCol = 4;          // the gate/door cell in row 1

// Grid cell of a room in the level (x = column, y = row; rooms at the same y
// in different columns are horizontally adjacent and therefore "connected"
// as far as the ROM is concerned).
struct GridPos {
    int x = 0;
    int y = 0;
};

std::string ShapeName(int mask) {
    if (mask == 0) {
        return "Sealed";
    }
    std::string name;
    auto add = [&name](const char* part) {
        name += name.empty() ? part : std::string("+") + part;
    };
    if (mask & SHAPE_N) add("N");
    if (mask & SHAPE_S) add("S");
    if (mask & SHAPE_H) add("H");
    if (mask & SHAPE_START) add("Start");
    if (mask & SHAPE_HOT) add("Hot");
    if (mask & SHAPE_GATE) add("Gate");
    if (mask & SHAPE_WATER) add("Water");
    return name;
}

ModelData MakeShapeModel(int modelId, int mask) {
    ModelData model;
    model.id = modelId;
    model.name = "Shape " + ShapeName(mask);
    model.width = kRoomWidth;
    model.height = kRoomHeight;
    model.tiles.assign(kRoomWidth * kRoomHeight, (int)TileType::AIR);
    // Border walls: rows 0 and 2 are full bands (a floor/ceiling row), and the
    // middle band's only wall is COL 0 — the mirrored OUTER edge. Col 9 is the
    // centre seam, NOT a boundary: a solid cell there would split the middle
    // band into two chambers and choke the vertical shaft (the live rooms keep
    // it open too: row 1 = "#.........").
    for (int x = 0; x < kRoomWidth; ++x) {
        model.tiles[x] = (int)TileType::SOLID_WALL;                    // row 0
        model.tiles[(kRoomHeight - 1) * kRoomWidth + x] =
            (int)TileType::SOLID_WALL;                                 // row 2
    }
    for (int y = 0; y < kRoomHeight; ++y) {
        model.tiles[y * kRoomWidth] = (int)TileType::SOLID_WALL;        // col 0
    }

    if (mask & SHAPE_N) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[x] = (int)TileType::AIR;
    }
    if (mask & SHAPE_S) {
        for (int x = kVertExitA; x <= kVertExitB; ++x)
            model.tiles[(kRoomHeight - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
    }
    if (mask & SHAPE_H) {
        for (int y = kHorizExitA; y <= kHorizExitB; ++y)
            model.tiles[y * kRoomWidth + kHorizExitCol] = (int)TileType::AIR;
    }
    if (mask & SHAPE_START) {
        // Level start rooms: the kernel drops the player in at LevelStartX/Y =
        // (32, 24) px = display col 8 = CELL 4 of the TOP band, and DropStep
        // bypasses collision — a solid band there would drop him INSIDE a wall.
        // Cells 2..9 open (the live stage's start room is "##........"), the
        // outer 16 px of the band staying solid.
        for (int x = 2; x < kRoomWidth; ++x)
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
        // Keyed gate: row 1 is a wall except ONE gap; the room's door patch
        // (LOCKED_DOOR) fills that gap and only the key opens it.
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[1 * kRoomWidth + x] =
                x == kGateCol ? (int)TileType::AIR : (int)TileType::SOLID_WALL;
        }
    }
    if (mask & SHAPE_WATER) {
        // Water goal: the bottom band is open, so the water strip shows and
        // kills; the raft floats on an open cell (row 2) and the miner waits
        // on row 1.
        for (int x = 1; x < kRoomWidth; ++x) {
            model.tiles[(kRoomHeight - 1) * kRoomWidth + x] =
                (int)TileType::AIR;
        }
    }
    return model;
}

std::vector<GridPos> LevelWalk(int rooms) {
    std::vector<GridPos> walk;
    walk.reserve(rooms);
    const int firstColumn = rooms < kColumnRooms ? rooms : kColumnRooms;
    for (int y = 0; y < firstColumn; ++y) {
        walk.push_back(GridPos{0, y});          // down column 0 (the start room)
    }
    for (int i = firstColumn; i < rooms; ++i) {
        walk.push_back(GridPos{1, kTurnY - (i - firstColumn)});   // up col 1
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
};

LevelPlan PlanFor(int level) {
    LevelPlan p;
    p.hot = level >= 3;
    p.water = level >= 4;
    p.gate = level >= 6;
    p.tentacle = level >= 7;
    p.extra = level >= 9;
    p.phase = level >= 11;      // the blink opens the gate for 45 frames
    p.hcrunch = level >= 14;    // crunch band sweeps the row-1 prefix
    p.patch = level >= 7;       // async block, now and then in normal rooms
    p.patch2 = level >= 12;     // two blocks (one per side) in that room
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
                  const GridPos& pos, int roomIndex, Role role) {
    int mask = 0;
    if (HasRoomAt(walk, pos.x, pos.y - 1)) mask |= SHAPE_N;
    if (HasRoomAt(walk, pos.x, pos.y + 1)) mask |= SHAPE_S;
    if (levelNumber > kColumnRooms && pos.y == kTurnY) mask |= SHAPE_H;
    if (roomIndex == 0) mask |= SHAPE_START;   // the level's spawn room
    if (role == Role::Hot) mask |= SHAPE_HOT;
    if (role == Role::Gate || role == Role::Phase) mask |= SHAPE_GATE;
    if (role == Role::WaterGoal) mask |= SHAPE_WATER;
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
              float rangeMax) {
    EnemyData e;
    e.type = (int)type;
    e.x = x;
    e.y = y;
    e.range_min = 0.0f;
    e.range_max = rangeMax;
    e.speed = speed;
    e.dir = 1;
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

void FillRoomObjects(int levelNumber, int roomIndex, int roomCount, Role role,
                     const LevelPlan& plan, RoomData& room) {
    if (roomIndex == roomCount - 1) {
        if (role == Role::WaterGoal) {
            // Water goal: the miner waits above the water; the raft ferries
            // (early levels) or a tentacle guards the surface (level 7+).
            room.bottom_band = true;
            room.bottom_r = 24;
            room.bottom_g = 88;
            room.bottom_b = 208;
            if (plan.tentacle) {
                AddEnemy(room, EnemyType::TENTACLE, 10.0f, 8.0f,
                         1.0f, 0.0f);
            } else {
                AddEnemy(room, EnemyType::RAFT, 4.0f, 8.0f, 1.0f, 0.0f);
            }
        } else if (roomCount > 1) {
            // Last room: the goal. A wall snake on the top band.
            AddEnemy(room, EnemyType::SNAKE, 1.0f, 3.0f,
                     1.5f + 0.5f * (levelNumber % 2), 4.0f);
        }
        return;
    }
    if (roomIndex == 0) {
        AddEnemy(room, EnemyType::SPIDER, 10.0f, 5.0f,
                 1.0f + 0.25f * (levelNumber % 4), 8.0f);
        return;
    }
    if (role == Role::Gate) {
        // Door rooms allow ONE non-key enemy (convert rule) — a bat.
        AddEnemy(room, EnemyType::BAT, 4.0f, 4.0f,
                 1.25f + 0.25f * (levelNumber % 4), 13.0f);
        return;
    }
    if (role == Role::Phase) {
        // Timing gate: the blink opens the row-1 gap; a bat still patrols.
        AddEnemy(room, EnemyType::BAT, 4.0f, 4.0f,
                 1.25f + 0.25f * (levelNumber % 4), 13.0f);
        return;
    }
    if (role == Role::Hcrunch) {
        // Convert rule: an hcrunch room has NO objects (the band owns the
        // sprite slot), so this room is empty on purpose.
        return;
    }
    if (role == Role::Hot) {
        AddEnemy(room, EnemyType::BAT, 4.0f, 4.0f,
                 1.25f + 0.25f * (levelNumber % 4), 13.0f);
        return;
    }
    // Normal room: bat/lamp. A LAMP only matters where the dark mask reaches
    // (rooms 0-7), so deeper rooms get a bat.
    if (roomIndex % 2 == 1 || roomIndex >= 8) {
        AddEnemy(room, EnemyType::BAT, 4.0f, 4.0f,
                 1.25f + 0.25f * (levelNumber % 4), 13.0f);
    } else {
        LampData lamp;
        lamp.x = 6.0f;
        lamp.y = 4.0f;
        lamp.lit = true;
        room.lamps.push_back(lamp);
    }
    if (plan.extra) {
        // Level 9+: a second object on a free row (cap = 2, one per row).
        if (!RowOccupied(room, 2)) {
            AddEnemy(room, EnemyType::SPIDER, 10.0f, 8.0f,
                     1.0f + 0.25f * (levelNumber % 4), 8.0f);
        } else if (!RowOccupied(room, 0)) {
            AddEnemy(room, EnemyType::SNAKE, 1.0f, 3.0f, 1.5f, 4.0f);
        }
    }
}

}  // namespace

void DataSerializer::Build20LevelStage(std::vector<LevelData>& levels,
                                       std::vector<ModelData>& models) {
    // 1. Every level's walk + the shape mask of each of its rooms. A room's
    //    ROLE (hot / gate / water goal) is part of the shape, so the library
    //    carries hazard variants as well as exit masks.
    std::vector<std::vector<GridPos>> walks(kStageLevels);
    std::vector<std::vector<int>> masks(kStageLevels);
    std::vector<std::vector<Role>> roles(kStageLevels);
    std::set<int> used;
    for (int l = 1; l <= kStageLevels; ++l) {
        // User rule 2026-10-20: 2 rooms is the floor, so level 1 has 2 rooms
        // and the serpentine still grows by one per level (2,2,3,...,20).
        walks[l - 1] = LevelWalk(l < 2 ? 2 : l);
        const LevelPlan plan = PlanFor(l);
        const int count = (int)walks[l - 1].size();
        for (int i = 0; i < count; ++i) {
            const Role role = RoleForRoom(i, count, plan);
            roles[l - 1].push_back(role);
            const int mask = RoomShapeMask(l, walks[l - 1], walks[l - 1][i],
                                           i, role);
            masks[l - 1].push_back(mask);
            used.insert(mask);
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
        level.miner_x = 4.0f;                 // clear of the bottom-centre hole
        level.miner_y = 7.0f;                 // convert hard-fails any other row
        level.miner_dir = 1;
        const LevelPlan plan = PlanFor(l);
        for (int i = 0; i < roomCount; ++i) {
            RoomData room;
            room.room_id = i;
            room.model_id = shapeId[masks[l - 1][i]];
            room.room_x = walks[l - 1][i].x;
            room.room_y = walks[l - 1][i].y;
            if (roles[l - 1][i] == Role::Gate) {
                // One LOCKED_DOOR cell in the gate gap (left/M1 side). Solid
                // until the level's key is held, then touch opens it.
                room.asym_patches.push_back(
                    {1, kGateCol, (int)TileType::LOCKED_DOOR, 1});
            }
            if (roles[l - 1][i] == Role::Phase) {
                // The gate gap blinks: 45 frames solid, 45 open.
                room.feature_cells.push_back(
                    {1, kGateCol, (int)TileType::PHASE});
            }
            if (roles[l - 1][i] == Role::Hcrunch) {
                // Fixed 10-cell prefix on the middle band (live stage form).
                for (int c = 0; c < kRoomWidth; ++c) {
                    room.feature_cells.push_back(
                        {1, c, (int)TileType::HCRUNCH});
                }
            }
            // Async BLOCKS: a plain solid patch (not a special) sprinkled
            // through ordinary rooms so async rides WITH enemies. The gate/
            // phase/hcrunch rooms keep their own special alone; the start and
            // goal rooms stay clean (spawn/pickup).
            if (roles[l - 1][i] == Role::Normal && i > 0
                    && i < roomCount - 1 && plan.patch && i % 3 == 2) {
                const int side = (i % 2 == 1) ? 1 : 0;   // M1 / ball half
                const int col = 2 + (i % 2);             // clear of the gap (4)
                room.asym_patches.push_back(
                    {1, col, (int)TileType::SOLID_WALL, side});
                if (plan.patch2) {
                    room.asym_patches.push_back(
                        {1, col, (int)TileType::SOLID_WALL, side == 0 ? 1 : 0});
                }
            }
            FillRoomObjects(l, i, roomCount, roles[l - 1][i], plan, room);
            level.rooms.push_back(room);
        }
        // Keys: one per gate, placed in the nearest earlier room that is not
        // another gate and has a free row (row 2 first). Row = y/4.
        for (int i = 1; i < roomCount; ++i) {
            if (roles[l - 1][i] != Role::Gate) continue;
            for (int j = i - 1; j >= 0; --j) {
                if (roles[l - 1][j] == Role::Gate) continue;
                if (roles[l - 1][j] == Role::Hcrunch) continue;  // no objects
                if (ObjectCount(level.rooms[j]) >= 2) continue;
                if (RowOccupied(level.rooms[j], 2)) continue;
                AddEnemy(level.rooms[j], EnemyType::KEY, 10.0f, 8.0f,
                         1.0f, 0.0f);
                break;
            }
        }
        levels.push_back(level);
    }
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
