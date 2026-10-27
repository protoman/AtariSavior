#pragma once
// One tile -> colour mapping for BOTH the room editor (MapCanvas) and the level
// map viewer (LevelMapWindow). 2026-10-27: the viewer had its own palette, drew
// every non-air tile as a plain wall and stamped async patches on the wrong
// half, so the map the user reads for level structure disagreed with the
// editor. Anything the editor can paint must go through here.
#include <QColor>

#include "LevelData.hpp"

namespace editor {

// `tileY` is the model row (= drawn band): odd bands use the level's second
// wall colour, like the kernel.
inline QColor TileColor(int tileType, int tileY, const QColor& wall,
                        const QColor& wall2) {
    switch (static_cast<hero::TileType>(tileType)) {
        case hero::TileType::AIR:
            return QColor(15, 15, 20);
        case hero::TileType::SOLID_WALL:
            return (tileY % 2 == 1) ? wall2 : wall;
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
        case hero::TileType::LOCKED_DOOR:
            return QColor(150, 154, 170);   // async door = grey 4clk stripe
        case hero::TileType::PHASE:
            return QColor(0, 180, 90);
        case hero::TileType::HCRUNCH:
            return QColor(0, 170, 200);
        default:
            return QColor(15, 15, 20);
    }
}

}  // namespace editor
