/*
 * Savior SDL - H.E.R.O. Level Editor
 * Atari 2600 TIA NTSC color palette (128 colors) and picker dialog.
 *
 * RGB values derived from the classic Stella NTSC 128-color chart
 * (luma 0-7 × hue 0-15). TIA colour byte = (luma << 4) | hue.
 */

#include "AtariPalette.hpp"
#include "NtscColorDialog.hpp"

#include <cmath>
#include <utility>

#include <QDialog>
#include <QDialogButtonBox>
#include <QGridLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

namespace editor {

// ---- palette data (hue-major: [hue][luma] = {R,G,B}) --------------------

static constexpr int kHues  = 16;
static constexpr int kLumas = 8;

static const QRgb kPalette[kHues][kLumas] = {
    // hue 0  grey
    {0x000000, 0x404040, 0x6c6c6c, 0x909090,
     0xb0b0b0, 0xc8c8c8, 0xdcdcdc, 0xececec},
    // hue 1  gold
    {0x444400, 0x646410, 0x848424, 0xa0a034,
     0xb8b840, 0xd0d050, 0xe8e85c, 0xfcfc68},
    // hue 2  orange
    {0x702800, 0x844414, 0x985c28, 0xac783c,
     0xbc8c4c, 0xcca05c, 0xdcb468, 0xe8cc7c},
    // hue 3  red-orange
    {0x841800, 0x983418, 0xac5030, 0xc06848,
     0xd0805c, 0xe09470, 0xeca880, 0xfcbc94},
    // hue 4  red
    {0x880000, 0x9c2020, 0xb03c3c, 0xc05858,
     0xd07070, 0xe08888, 0xeca0a0, 0xfcb4b4},
    // hue 5  magenta
    {0x78005c, 0x8c2074, 0xa03c88, 0xb0589c,
     0xc070b0, 0xd084c0, 0xdc9cd0, 0xecb0e0},
    // hue 6  purple
    {0x480078, 0x602090, 0x783ca4, 0x8c58b8,
     0xa070cc, 0xb484dc, 0xc49cec, 0xd4b0fc},
    // hue 7  blue-violet
    {0x140084, 0x302098, 0x4c3cac, 0x6858c0,
     0x7c70d0, 0x9488e0, 0xa8a0ec, 0xbcb4fc},
    // hue 8  blue
    {0x000088, 0x1c209c, 0x3840b0, 0x505cc0,
     0x6874d0, 0x7c8ce0, 0x90a4ec, 0xa4b8fc},
    // hue 9  light blue
    {0x00187c, 0x1c3890, 0x3854a8, 0x5070bc,
     0x6888cc, 0x7c9cdc, 0x90b4ec, 0xa4c8fc},
    // hue A  sky blue
    {0x002c5c, 0x1c4c78, 0x386890, 0x5084ac,
     0x689cc0, 0x7cb4d4, 0x90cce8, 0xa4e0fc},
    // hue B  teal
    {0x00402c, 0x1c5c48, 0x387c64, 0x509c80,
     0x68b494, 0x7cd0ac, 0x90e4c0, 0xa4fcd4},
    // hue C  green
    {0x003c00, 0x205c20, 0x407c40, 0x5c9c5c,
     0x74b474, 0x8cd08c, 0xa4e4a4, 0xb8fcb8},
    // hue D  yellow-green
    {0x143800, 0x345c1c, 0x507c38, 0x6c9850,
     0x84b468, 0x9ccc7c, 0xb4e490, 0xc8fca4},
    // hue E  olive
    {0x2c3000, 0x4c501c, 0x687034, 0x848c4c,
     0x9ca864, 0xb4c078, 0xccd488, 0xe0ec9c},
    // hue F  brown
    {0x442800, 0x644818, 0x846830, 0xa08444,
     0xb89c5c, 0xd0b46c, 0xfce08c, 0xffee94},
};

static const QString kHueNames[kHues] = {
    "grey",      "gold",      "orange",     "red-orange",
    "red",       "magenta",   "purple",     "blue-violet",
    "blue",      "light blue","sky blue",   "teal",
    "green",     "yellow-grn","olive",      "brown",
};

// ---- helpers ---------------------------------------------------------------

QColor NtscRgb(int hue, int luma) {
    hue  = std::max(0, std::min(15, hue));
    luma = std::max(0, std::min(7,  luma));
    return QColor::fromRgb(kPalette[hue][luma]);
}

QColor NtscRgbForByte(int colorByte) {
    return NtscRgb(colorByte & 0x0F, (colorByte >> 4) & 0x0F);
}

int NtscHue(int colorByte)       { return colorByte & 0x0F; }
int NtscLuma(int colorByte)      { return (colorByte >> 4) & 0x0F; }
QString NtscHueName(int hue)     { return kHueNames[hue & 0x0F]; }

int NearestNtscByte(const QColor& color) {
    int bestByte = 0;
    int bestDist = INT_MAX;
    for (int luma = 0; luma < kLumas; ++luma) {
        for (int hue = 0; hue < kHues; ++hue) {
            QRgb p = kPalette[hue][luma];
            int dr = color.red()   - qRed(p);
            int dg = color.green() - qGreen(p);
            int db = color.blue()  - qBlue(p);
            int dist = dr*dr + dg*dg + db*db;
            if (dist < bestDist) {
                bestDist = dist;
                bestByte = (luma << 4) | hue;
            }
        }
    }
    return bestByte;
}

// ---- NTSC colour picker dialog -------------------------------------------

NtscColorDialog::NtscColorDialog(QWidget* parent, int currentByte)
    : QDialog(parent), m_byte(currentByte >= 0 ? currentByte : 0x2A) {
    setWindowTitle("Atari 2600 NTSC Colour");
    auto* outer = new QVBoxLayout(this);

        auto* header = new QLabel("Select a TIA colour byte for the game ROM");
        outer->addWidget(header);

        auto* grid = new QGridLayout();
        grid->setContentsMargins(0,0,0,0);
        grid->setSpacing(2);
        for (int col = 0; col < kHues; ++col) {
            auto* lbl = new QLabel(QString::number(col, 16).toUpper());
            lbl->setAlignment(Qt::AlignHCenter);
            lbl->setFixedWidth(28);
            grid->addWidget(lbl, 0, col + 1);
        }
        for (int row = 0; row < kLumas; ++row) {
            int lumaNibble = row;
            auto* lbl = new QLabel(QString::number(lumaNibble << 4, 16).toUpper() + "x");
            lbl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
            lbl->setFixedWidth(28);
            grid->addWidget(lbl, row + 1, 0);
            for (int col = 0; col < kHues; ++col) {
                int byte = (row << 4) | col;
                auto* btn = new QPushButton();
                btn->setFixedSize(28, 20);
                btn->setToolTip(QString("$%1  %2  luma %3")
                    .arg(byte, 2, 16, QChar('0'))
                    .arg(kHueNames[col]).arg(row));
                QColor c = NtscRgb(col, row);
                btn->setStyleSheet(QString("background-color: rgb(%1,%2,%3);")
                    .arg(c.red()).arg(c.green()).arg(c.blue()));
                connect(btn, &QPushButton::clicked, this, [this, byte]{ selectByte(byte); });
                grid->addWidget(btn, row + 1, col + 1);
                m_buttons.push_back(btn);
            }
        }
        outer->addLayout(grid);

        // preview row
        auto* prevRow = new QHBoxLayout();
        m_previewBox = new QLabel();
        m_previewBox->setFixedSize(32, 20);
        prevRow->addWidget(m_previewBox);
        m_infoLabel = new QLabel();
        prevRow->addWidget(m_infoLabel);
        prevRow->addStretch();
        outer->addLayout(prevRow);

        auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
        connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
        outer->addWidget(buttons);
        setFixedWidth(kHues * 30 + 60);

        // highlight current
        selectByte(m_byte);
}

void NtscColorDialog::selectByte(int byte) {
    m_byte = byte;
    QRgb p = kPalette[NtscHue(byte)][NtscLuma(byte)];
    QColor c = QColor::fromRgb(p);
    m_previewBox->setStyleSheet(QString("background-color: rgb(%1,%2,%3);")
        .arg(c.red()).arg(c.green()).arg(c.blue()));
    m_infoLabel->setText(QString("$%1  %2  luma %3")
        .arg(byte, 2, 16, QChar('0'))
        .arg(kHueNames[NtscHue(byte)])
        .arg(NtscLuma(byte)));
    for (int i = 0; i < (int)m_buttons.size(); ++i) {
        int h = i % kHues;
        int l = i / kHues;
        bool sel = (i == byte);
        QRgb pp = kPalette[h][l];
        QColor cc = QColor::fromRgb(pp);
        QString border = sel ? "2px solid white;" : "none;";
        m_buttons[i]->setStyleSheet(QString(
            "background-color: rgb(%1,%2,%3); border: %4")
            .arg(cc.red()).arg(cc.green()).arg(cc.blue()).arg(border));
    }
}

int PickNtscColor(QWidget* parent, const QColor& current) {
    NtscColorDialog dlg(parent, NearestNtscByte(current));
    if (dlg.exec() == QDialog::Accepted)
        return dlg.selectedByte();
    return -1;
}

} // namespace editor