#include "LevelMapWindow.hpp"

#include <QColor>
#include <QFont>
#include <QPainter>
#include <QPixmap>
#include <QScrollArea>
#include <QVBoxLayout>

#include <algorithm>

namespace editor {

namespace {

// HERO-atlas geometry: a room is the FULL mirrored stage (40 display columns
// x 12 display rows, the same mapping the level canvas uses), and linked
// rooms are drawn FLUSH — no gap, no link strip. A carved opening then shows
// as a real passage between two rooms, exactly like a HERO map sheet.
constexpr int kCols = 40;      // display columns (10 cells x 2, mirrored)
// 3x the readable minimum (user 2026-10-21): a room is a 480 x 216 canvas,
// so the scroll area shows a HERO-like sheet at a comfortable size.
constexpr int kColW = 12;      // px per display column
constexpr int kRows = 12;      // display rows (4 bands x 3 rows): the
                               // cave is 144 px = 12 x 12-px rows and a
                               // band is 36 lines = 3 rows (N=4)
constexpr int kRowH = 18;      // px per display row
constexpr int kRoomW = kCols * kColW;   // 480 px
constexpr int kRoomH = kRows * kRowH;   // 216 px
constexpr int kMargin = 16;
constexpr int kHeader = 22;
constexpr int kGrid = 15;      // C1: nibble 15 is the no-room sentinel

struct RoomView {
    int id = 0;
    int x = 0, y = 0;
    QString rows[hero::kRoomHeight];
    bool start = false;
    bool miner = false;
    bool water = false;
    float minerX = 0.0f;   // game px, only meaningful in the miner room
    float minerY = 0.0f;
    std::vector<QPointF> extraMiners;   // display col, stage row (record type 15)
};

}  // namespace

// ---------------------------------------------------------------------------
// LevelMapView — the painting surface (read-only).
// ---------------------------------------------------------------------------
class LevelMapView : public QWidget {
public:
    explicit LevelMapView(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(2 * kMargin + kGrid * kRoomW,
                       kHeader + 2 * kMargin + kGrid * kRoomH);
    }

    void SetData(std::vector<RoomView> rooms, int levelNumber,
                 QColor wall1, QColor wall2) {
        m_rooms = std::move(rooms);
        m_level = levelNumber;
        m_wall1 = wall1;
        m_wall2 = wall2;
        int maxX = 0, maxY = 0;
        for (const RoomView& r : m_rooms) {
            maxX = std::max(maxX, r.x);
            maxY = std::max(maxY, r.y);
        }
        setMinimumSize(2 * kMargin + (maxX + 1) * kRoomW,
                       kHeader + 2 * kMargin + (maxY + 1) * kRoomH + 18);
        update();
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.fillRect(rect(), QColor(12, 12, 20));

        for (const RoomView& r : m_rooms) {
            const int ox = kMargin + r.x * kRoomW;
            const int oy = kHeader + kMargin + r.y * kRoomH;
            // Display column -> model cell (mirrored half, 2 cols per cell).
            for (int row = 0; row < kRows; ++row) {
                // 12-px display rows per DRAWN band: 36 lines / 12 = 3
                // (was /4 while a band was 48 lines of 4 rows).
                const int band = row / 3;
                for (int dcol = 0; dcol < kCols; ++dcol) {
                    const int src = (dcol < kCols / 2) ? dcol
                                                      : (kCols - 1 - dcol);
                    const int cell = src / 2;
                    const char t = r.rows[band][cell].toLatin1();
                    QColor col(32, 32, 44);                 // air
                    if (t == '#' || t == 'C') col = m_wall1;
                    else if (t == 'H') col = QColor(214, 58, 40);
                    else if (t == 'D') col = QColor(232, 196, 48);
                    else if (t == 'P') col = QColor(64, 196, 224);
                    else if (t == 'W') col = QColor(28, 72, 176);
                    // Band 1 uses the room's second wall color (kernel rule).
                    if (t == '#' && band == 1) col = m_wall2;
                    p.fillRect(ox + dcol * kColW, oy + row * kRowH,
                               kColW, kRowH, col);
                }
            }
            // Miner dot at its game position (room px -> display grid).
            if (r.miner) {
                const int mx = ox + (int)(r.minerX * 2.0f) * kColW;
                const int my = oy + (int)r.minerY * kRowH;
                p.setPen(Qt::NoPen);
                p.setBrush(QColor(255, 140, 180));
                p.drawEllipse(QPoint(mx + kColW / 2, my + kRowH / 2), 6, 6);
            }
            // Extra miners (record type 15): same pink dot, smaller.
            for (const QPointF& m : r.extraMiners) {
                p.setPen(Qt::NoPen);
                p.setBrush(QColor(255, 140, 180));
                p.drawEllipse(QPoint(ox + (int)m.x() * kColW + kColW / 2,
                                     oy + (int)m.y() * kRowH + kRowH / 2), 5, 5);
            }
            QFont small = font();
            small.setPixelSize(11);
            small.setBold(true);
            p.setFont(small);
            QString tag = QString::number(r.id + 1);   // user counts from 1
            if (r.start) tag += "S";
            if (r.miner) tag += "M";
            if (!r.extraMiners.empty()) tag += QString("m%1").arg((int)r.extraMiners.size());
            const QRect tagRect(ox + 2, oy + 2, 14 + 8 * tag.size(), 14);
            p.fillRect(tagRect, QColor(0, 0, 0, 170));
            p.setPen(QColor(235, 235, 240));
            p.drawText(tagRect.adjusted(3, 1, 0, 0), Qt::AlignLeft, tag);
        }

        // Room divider guides (user 2026-10-21, HERO atlas style): a grid of
        // room-sized cells across the whole canvas. Drawn ON TOP of the rooms
        // so a passage keeps a visible seam at the room border.
        p.setPen(QPen(QColor(125, 125, 150), 1));
        for (int x = kMargin; x <= width(); x += kRoomW)
            p.drawLine(x, 0, x, height());
        for (int y = kHeader + kMargin; y <= height(); y += kRoomH)
            p.drawLine(0, y, width(), y);

        p.setPen(QColor(220, 220, 230));
        QFont head = font();
        head.setPixelSize(11);
        p.setFont(head);
        p.drawText(kMargin, kHeader - 6,
                   QString("Level %1 map — %2 rooms (linked rooms are flush)")
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
    resize(1000, 760);
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
        v.minerX = level.miner_x;   // CELL units (display col = x * 2)
        v.minerY = level.miner_y;   // display row (kernel: 7 = 84 px)
        for (const hero::EnemyData& e : room.enemies) {
            if (e.type == (int)hero::EnemyType::EXTRA_MINER)
                v.extraMiners.push_back(QPointF(e.x, e.y));
        }
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
