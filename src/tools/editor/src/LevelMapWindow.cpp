#include "LevelMapWindow.hpp"

#include <QColor>
#include <QFont>
#include <QPainter>
#include <QScrollArea>
#include <QVBoxLayout>
#include <QPixmap>

#include <algorithm>

namespace editor {

namespace {

constexpr int kCellW = 8;      // px per room cell (10 cells x 3 bands)
constexpr int kCellH = 8;
constexpr int kRoomW = hero::kRoomWidth * kCellW;      // 60
constexpr int kRoomH = hero::kRoomHeight * kCellH;     // 18
constexpr int kGap = 24;       // gap between room boxes (link corridor)
constexpr int kStep = kRoomW + kGap;
constexpr int kMargin = 16;
constexpr int kHeader = 22;    // title line above the grid
constexpr int kGrid = 15;      // C1: nibble 15 is the no-room sentinel

struct RoomView {
    int id = 0;
    int x = 0, y = 0;
    QString rows[hero::kRoomHeight];
    bool start = false;
    bool miner = false;
    bool water = false;
};

bool Open(char c) { return c == '.' || c == 'W'; }

}  // namespace

// ---------------------------------------------------------------------------
// LevelMapView — the painting surface (read-only).
// ---------------------------------------------------------------------------
class LevelMapView : public QWidget {
public:
    explicit LevelMapView(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(2 * kMargin + kGrid * kStep,
                       kHeader + 2 * kMargin + kGrid * kStep);
    }

    void SetData(std::vector<RoomView> rooms, int levelNumber,
                 QColor wall1, QColor wall2) {
        m_rooms = std::move(rooms);
        m_level = levelNumber;
        m_wall1 = wall1;
        m_wall2 = wall2;
        // Fit the actual extent so a small level opens in a small window.
        int maxX = 0, maxY = 0;
        for (const RoomView& r : m_rooms) {
            maxX = std::max(maxX, r.x);
            maxY = std::max(maxY, r.y);
        }
        setMinimumSize(2 * kMargin + (maxX + 1) * kStep,
                       kHeader + 2 * kMargin + (maxY + 1) * kStep + 18);
        update();
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.fillRect(rect(), QColor(12, 12, 20));
        p.setRenderHint(QPainter::Antialiasing, false);

        const RoomView* at[kGrid][kGrid] = {};
        for (const RoomView& r : m_rooms) {
            if (r.x >= 0 && r.x < kGrid && r.y >= 0 && r.y < kGrid)
                at[r.x][r.y] = &r;
        }

        // Links first (under the room boxes), so a corridor visually joins.
        p.setPen(Qt::NoPen);
        p.setBrush(QColor(150, 150, 90));
        for (int y = 0; y < kGrid; ++y) {
            for (int x = 0; x < kGrid; ++x) {
                const RoomView* a = at[x][y];
                if (!a) continue;
                const RoomView* south = (y + 1 < kGrid) ? at[x][y + 1] : nullptr;
                if (south) {
                    for (int c = 0; c < hero::kRoomWidth; ++c) {
                        if (!Open(a->rows[2][c].toLatin1())) continue;
                        if (!Open(south->rows[0][c].toLatin1())) continue;
                        const int px = kMargin + x * kStep + c * kCellW;
                        const int py = kHeader + kMargin + y * kStep + kRoomH;
                        p.drawRect(px, py, kCellW, kGap);
                    }
                }
                const RoomView* east = (x + 1 < kGrid) ? at[x + 1][y] : nullptr;
                if (east) {
                    // Mirrored playfield: cell 0 is BOTH side edges, so a
                    // horizontal passage needs cell 0 cut in both rooms.
                    if (Open(a->rows[1][0].toLatin1())
                            && Open(east->rows[1][0].toLatin1())) {
                        const int px = kMargin + x * kStep + kRoomW;
                        const int py = kHeader + kMargin + y * kStep + kCellH;
                        p.drawRect(px, py, kGap, kCellH);
                    }
                }
            }
        }

        QFont small = font();
        small.setPixelSize(9);
        for (const RoomView& r : m_rooms) {
            const int ox = kMargin + r.x * kStep;
            const int oy = kHeader + kMargin + r.y * kStep;
            for (int row = 0; row < hero::kRoomHeight; ++row) {
                for (int c = 0; c < hero::kRoomWidth; ++c) {
                    const char t = r.rows[row][c].toLatin1();
                    QColor col(32, 32, 44);                 // air
                    if (t == '#' || t == 'C') col = m_wall1;
                    else if (t == 'H') col = QColor(214, 58, 40);   // hot
                    else if (t == 'D') col = QColor(232, 196, 48);  // door
                    else if (t == 'P') col = QColor(64, 196, 224);  // phase
                    else if (t == 'W') col = QColor(28, 72, 176);   // water
                    p.fillRect(ox + c * kCellW, oy + row * kCellH,
                               kCellW, kCellH, col);
                }
            }
            // Row-1 walls use the second wall color (kernel band color).
            for (int c = 0; c < hero::kRoomWidth; ++c) {
                const char t = r.rows[1][c].toLatin1();
                if (t == '#')
                    p.fillRect(ox + c * kCellW, oy + kCellH, kCellW, kCellH,
                               m_wall2);
            }
            // Frame: start room green, miner room gold, other rooms grey.
            QColor frame(96, 96, 110);
            int pen = 1;
            if (r.start) { frame = QColor(80, 220, 120); pen = 2; }
            if (r.miner) { frame = QColor(240, 200, 90); pen = 2; }
            p.setPen(QPen(frame, pen));
            p.setBrush(Qt::NoBrush);
            p.drawRect(ox - 1, oy - 1, kRoomW + 2, kRoomH + 2);

            p.setFont(small);
            p.setPen(QColor(170, 170, 180));
            QString tag = QString::number(r.id + 1);   // user counts from 1
            if (r.start) tag += " S";
            if (r.miner) tag += " M";
            if (r.water) tag += " W";
            p.drawText(ox, oy + kRoomH + 12, tag);
        }

        p.setPen(QColor(220, 220, 230));
        QFont head = font();
        head.setPixelSize(11);
        p.setFont(head);
        p.drawText(kMargin, kHeader - 6,
                   QString("Level %1 map — %2 rooms")
                       .arg(m_level).arg((int)m_rooms.size()));
    }

private:
    std::vector<RoomView> m_rooms;
    int m_level = 1;
    QColor m_wall1{160, 160, 170};
    QColor m_wall2{120, 170, 130};
};

// ---------------------------------------------------------------------------
// LevelMapWindow — scrollable dialog wrapper.
// ---------------------------------------------------------------------------
LevelMapWindow::LevelMapWindow(QWidget* parent) : QDialog(parent) {
    setWindowTitle("Level Map");
    resize(900, 700);
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    m_scroll = new QScrollArea(this);
    m_scroll->setWidgetResizable(true);
    layout->addWidget(m_scroll);
    m_view = new LevelMapView(m_scroll);
    m_scroll->setWidget(m_view);
}

QPixmap LevelMapWindow::RenderPixmap() {
    m_view->resize(m_view->minimumSize());
    QPixmap pix(m_view->size());
    pix.fill(QColor(12, 12, 20));
    m_view->render(&pix);
    return pix;
}

void LevelMapWindow::SetLevel(const hero::LevelData& level,
                              const std::vector<hero::ModelData>& models,
                              int levelNumber) {
    std::vector<RoomView> rooms;
    rooms.reserve(level.rooms.size());
    const int minerRoom = level.miner_room & 0x7F;
    for (const hero::RoomData& room : level.rooms) {
        const hero::ModelData* model = nullptr;
        for (const hero::ModelData& m : models) {
            if (m.id == room.model_id) { model = &m; break; }
        }
        RoomView v;
        v.id = room.room_id;
        v.x = room.room_x;
        v.y = room.room_y;
        v.start = (room.room_id == level.start_room);
        v.miner = (room.room_id == minerRoom);
        v.water = room.bottom_band;
        for (int row = 0; row < hero::kRoomHeight; ++row) {
            QString line(hero::kRoomWidth, '.');
            if (model) {
                const int w = model->width > 0 ? model->width
                                               : hero::kRoomWidth;
                for (int c = 0; c < hero::kRoomWidth; ++c) {
                    const int idx = row * w + c;
                    if (idx < (int)model->tiles.size()
                            && model->tiles[idx] != (int)hero::TileType::AIR) {
                        line[c] = '#';       // solid (hot flagged below)
                    }
                }
                if (row == 1 && model->mid_band_type == 1) {
                    for (int c = 0; c < hero::kRoomWidth; ++c)
                        if (line[c] == '#') line[c] = 'H';
                }
            }
            if (room.bottom_band && row == 2) {
                for (int c = 0; c < hero::kRoomWidth; ++c)
                    if (line[c] == '.') line[c] = 'W';
            }
            v.rows[row] = line;
        }
        for (const auto& patch : room.asym_patches) {
            if (patch.size() < 3) continue;
            const int row = patch[0], col = patch[1], tile = patch[2];
            if (row < 0 || row >= hero::kRoomHeight
                    || col < 0 || col >= hero::kRoomWidth) continue;
            v.rows[row][col] = (tile == (int)hero::TileType::LOCKED_DOOR)
                                   ? 'D' : '#';
        }
        for (const auto& feat : room.feature_cells) {
            if (feat.size() < 3) continue;
            const int row = feat[0], col = feat[1], tile = feat[2];
            if (row < 0 || row >= hero::kRoomHeight
                    || col < 0 || col >= hero::kRoomWidth) continue;
            v.rows[row][col] = (tile == (int)hero::TileType::PHASE)
                                   ? 'P' : 'C';
        }
        rooms.push_back(std::move(v));
    }
    m_view->SetData(std::move(rooms), levelNumber,
                    QColor(level.wall_r, level.wall_g, level.wall_b),
                    QColor(level.wall2_r, level.wall2_g, level.wall2_b));
    setWindowTitle(QString("Level %1 Map").arg(levelNumber));
}

bool RenderLevelMapPng(const hero::LevelData& level,
                       const std::vector<hero::ModelData>& models,
                       int levelNumber, const QString& path) {
    LevelMapWindow window;          // same code path as the View -> Map window
    window.SetLevel(level, models, levelNumber);
    const QPixmap pix = window.RenderPixmap();
    return pix.save(path);
}

}  // namespace editor
