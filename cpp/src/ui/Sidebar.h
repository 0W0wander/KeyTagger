#pragma once

#include <QWidget>
#include <QSet>

class QLineEdit;
class QSlider;
class QPushButton;
class QVBoxLayout;
class QScrollArea;
class QCheckBox;
class QLabel;
class QTabWidget;

namespace KeyTagger {

class Database;
class Config;

/**
 * Sidebar - Left panel with controls and tag filters
 * 
 * Features:
 * - Folder picker and scan controls
 * - Thumbnail size slider
 * - Tag filter checkboxes with counts
 * - Hotkey configuration
 * - Mode toggles (viewing, tagging)
 */
class Sidebar : public QWidget {
    Q_OBJECT

public:
    explicit Sidebar(Database* db, QWidget* parent = nullptr);
    
    void setDarkMode(bool dark);
    void refreshTags();
    
    QString currentFolder() const;
    void setCurrentFolder(const QString& path);
    
    int thumbnailSize() const;
    
    QSet<QString> selectedFilterTags() const;
    bool showUntaggedOnly() const;

signals:
    void pickFolderClicked();
    void scanFolderClicked();
    void settingsClicked();
    void openDatabaseFolderClicked();
    void viewingModeToggled(bool enabled);
    void taggingModeToggled(bool enabled);
    void thumbnailSizeChanged(int size);
    void filterChanged();
    void hotkeyAdded(const QString& key, const QString& tag);
    void hotkeyRemoved(const QString& key);

private slots:
    void onThumbnailSliderChanged(int value);
    void onTagCheckboxToggled(bool checked);
    void onUntaggedToggled(bool checked);
    void onAddHotkeyClicked();
    void onRemoveHotkeyClicked();

private:
    void setupUi();
    void setupGeneralTab(QWidget* tab);
    void setupTagsTab(QWidget* tab);
    void rebuildHotkeyList();
    void rebuildTagList();
    void applyTheme();
    
    Database* m_db;
    bool m_darkMode = true;
    
    // UI Elements
    QTabWidget* m_tabWidget = nullptr;
    
    // General tab
    QLineEdit* m_folderEdit = nullptr;
    QPushButton* m_pickFolderBtn = nullptr;
    QPushButton* m_scanFolderBtn = nullptr;
    QSlider* m_thumbSlider = nullptr;
    QLabel* m_thumbSizeLabel = nullptr;
    QPushButton* m_settingsBtn = nullptr;
    QPushButton* m_dbFolderBtn = nullptr;
    
    // Tags tab
    QWidget* m_tagListWidget = nullptr;
    QVBoxLayout* m_tagListLayout = nullptr;
    QCheckBox* m_untaggedCheckbox = nullptr;
    QHash<QString, QCheckBox*> m_tagCheckboxes;
    
    // Hotkeys
    QLineEdit* m_hotkeyKeyEdit = nullptr;
    QLineEdit* m_hotkeyTagEdit = nullptr;
    QPushButton* m_addHotkeyBtn = nullptr;
    QWidget* m_hotkeyListWidget = nullptr;
    QVBoxLayout* m_hotkeyListLayout = nullptr;
    
    // Mode buttons
    QPushButton* m_viewingModeBtn = nullptr;
    QPushButton* m_taggingModeBtn = nullptr;
    
    // Filter state
    QSet<QString> m_selectedTags;
    bool m_showUntagged = false;
};

} // namespace KeyTagger

