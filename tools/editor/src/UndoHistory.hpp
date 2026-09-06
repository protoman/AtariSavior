/*
 * Savior SDL - H.E.R.O. Level Editor
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

#include <cstddef>
#include <vector>

namespace editor {

// Tracks document states for undo and detects unsaved (dirty) modifications.
// A freshly constructed history holds no document and reports NOT modified,
// so the editor must never prompt to save before a level is loaded/created.
template <typename T>
class UndoHistory {
public:
    explicit UndoHistory(std::size_t maxStates = 50) : m_maxStates(maxStates) {}

    // Replaces all history when a new document is created or loaded.
    void Reset(const T& state) {
        m_states.clear();
        m_states.push_back(state);
        m_index = 0;
        m_cleanIndex = 0;
    }

    // Records a modification of the document, dropping any redo states.
    void Push(const T& state) {
        if (m_states.empty()) {
            Reset(state);
            return;
        }
        m_states.erase(m_states.begin() + m_index + 1, m_states.end());
        m_states.push_back(state);
        m_index = static_cast<int>(m_states.size()) - 1;
        Trim();
    }

    // Restores the previous state; returns false when already at the oldest one.
    bool Undo(T& outState) {
        if (!CanUndo()) return false;
        --m_index;
        outState = m_states[static_cast<std::size_t>(m_index)];
        return true;
    }

    bool CanUndo() const { return m_index > 0; }

    bool IsModified() const { return m_index != m_cleanIndex; }

    // Marks the current state as saved (clean).
    void SetClean() { m_cleanIndex = m_index; }

private:
    void Trim() {
        while (m_states.size() > m_maxStates) {
            m_states.erase(m_states.begin());
            --m_index;
            if (m_cleanIndex > 0) {
                --m_cleanIndex;
            } else if (m_cleanIndex == 0) {
                m_cleanIndex = -1; // Clean state was evicted from the front
            }
        }
    }

    std::vector<T> m_states;
    int m_index = -1;
    int m_cleanIndex = -1;
    std::size_t m_maxStates;
};

} // namespace editor
