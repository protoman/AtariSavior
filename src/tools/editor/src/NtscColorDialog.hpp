/*
 * Savior SDL - H.E.R.O. Level Editor
 * Atari 2600 NTSC colour picker dialog.
 */

#pragma once

#include <QDialog>
#include <QPushButton>
#include <QLabel>
#include <vector>

namespace editor {

// Modal NTSC palette grid picker; returns the chosen TIA colour byte or -1.
class NtscColorDialog : public QDialog {
    Q_OBJECT
public:
    explicit NtscColorDialog(QWidget* parent, int currentByte);
    int selectedByte() const { return m_byte; }

private slots:
    void selectByte(int byte);

private:
    int m_byte = 0;
    std::vector<QPushButton*> m_buttons;
    QLabel* m_previewBox = nullptr;
    QLabel* m_infoLabel = nullptr;
};

} // namespace editor