#include "Sidebar.h"
#include "Database.h"
#include "Config.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLineEdit>
#include <QSlider>
#include <QPushButton>
#include <QLabel>
#include <QTabWidget>
#include <QScrollArea>
#include <QCheckBox>
#include <QFrame>
#include <QDebug>

namespace KeyTagger {

Sidebar::Sidebar(Database* db, QWidget* parent)
    : QWidget(parent)
    , m_db(db)
{
    setupUi();
    applyTheme();
}

void Sidebar::setupUi() {
    setFixedWidth(280);
    
    QVBoxLayout* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(12, 12, 12, 12);
    mainLayout->setSpacing(8);
    
    // Title
    QLabel* titleLabel = new QLabel("KeyTagger", this);
    titleLabel->setObjectName("titleLabel");
    QFont titleFont = titleLabel->font();
    titleFont.setPointSize(16);
    titleFont.setBold(true);
    titleLabel->setFont(titleFont);
    mainLayout->addWidget(titleLabel);
    
    // Tab widget
    m_tabWidget = new QTabWidget(this);
    m_tabWidget->setDocumentMode(true);
    mainLayout->addWidget(m_tabWidget, 1);
    
    // General tab
    QWidget* generalTab = new QWidget();
    setupGeneralTab(generalTab);
    m_tabWidget->addTab(generalTab, "General");
    
    // Tags & Hotkeys tab
    QWidget* tagsTab = new QWidget();
    setupTagsTab(tagsTab);
    m_tabWidget->addTab(tagsTab, "Tags & Hotkeys");
}

void Sidebar::setupGeneralTab(QWidget* tab) {
    QVBoxLayout* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(0, 8, 0, 0);
    layout->setSpacing(8);
    
    // Folder buttons
    QHBoxLayout* folderBtnLayout = new QHBoxLayout();
    m_pickFolderBtn = new QPushButton("Pick Folder", tab);
    m_pickFolderBtn->setObjectName("pickFolderBtn");
    m_scanFolderBtn = new QPushButton("Scan Folder", tab);
    m_scanFolderBtn->setObjectName("scanFolderBtn");
    folderBtnLayout->addWidget(m_pickFolderBtn);
    folderBtnLayout->addWidget(m_scanFolderBtn);
    layout->addLayout(folderBtnLayout);
    
    connect(m_pickFolderBtn, &QPushButton::clicked, this, &Sidebar::pickFolderClicked);
    connect(m_scanFolderBtn, &QPushButton::clicked, this, &Sidebar::scanFolderClicked);
    
    // Folder path
    m_folderEdit = new QLineEdit(tab);
    m_folderEdit->setReadOnly(true);
    m_folderEdit->setPlaceholderText("No folder selected");
    layout->addWidget(m_folderEdit);
    
    // Separator
    QFrame* sep1 = new QFrame(tab);
    sep1->setFrameShape(QFrame::HLine);
    sep1->setObjectName("separator");
    layout->addWidget(sep1);
    
    // Thumbnail size
    QLabel* thumbLabel = new QLabel("Thumbnail size", tab);
    thumbLabel->setObjectName("mutedLabel");
    layout->addWidget(thumbLabel);
    
    QHBoxLayout* thumbLayout = new QHBoxLayout();
    m_thumbSlider = new QSlider(Qt::Horizontal, tab);
    m_thumbSlider->setRange(120, 512);
    m_thumbSlider->setValue(Config::instance().thumbnailSize());
    thumbLayout->addWidget(m_thumbSlider);
    
    m_thumbSizeLabel = new QLabel(QString::number(m_thumbSlider->value()) + "px", tab);
    m_thumbSizeLabel->setFixedWidth(50);
    thumbLayout->addWidget(m_thumbSizeLabel);
    layout->addLayout(thumbLayout);
    
    connect(m_thumbSlider, &QSlider::valueChanged, this, &Sidebar::onThumbnailSliderChanged);
    
    // Separator
    QFrame* sep2 = new QFrame(tab);
    sep2->setFrameShape(QFrame::HLine);
    sep2->setObjectName("separator");
    layout->addWidget(sep2);
    
    // Settings button
    m_settingsBtn = new QPushButton("Settings", tab);
    layout->addWidget(m_settingsBtn);
    connect(m_settingsBtn, &QPushButton::clicked, this, &Sidebar::settingsClicked);
    
    // Open database folder button
    m_dbFolderBtn = new QPushButton("Open Database Folder", tab);
    m_dbFolderBtn->setObjectName("smallBtn");
    layout->addWidget(m_dbFolderBtn);
    connect(m_dbFolderBtn, &QPushButton::clicked, this, &Sidebar::openDatabaseFolderClicked);
    
    layout->addStretch();
}

void Sidebar::setupTagsTab(QWidget* tab) {
    QVBoxLayout* layout = new QVBoxLayout(tab);
    layout->setContentsMargins(0, 8, 0, 0);
    layout->setSpacing(8);
    
    // Hotkey add section
    QLabel* hotkeyTitle = new QLabel("Add Hotkey", tab);
    hotkeyTitle->setObjectName("sectionTitle");
    layout->addWidget(hotkeyTitle);
    
    QHBoxLayout* hotkeyAddLayout = new QHBoxLayout();
    m_hotkeyKeyEdit = new QLineEdit(tab);
    m_hotkeyKeyEdit->setPlaceholderText("Key (e.g., z)");
    m_hotkeyKeyEdit->setFixedWidth(80);
    hotkeyAddLayout->addWidget(m_hotkeyKeyEdit);
    
    m_hotkeyTagEdit = new QLineEdit(tab);
    m_hotkeyTagEdit->setPlaceholderText("Tag name");
    hotkeyAddLayout->addWidget(m_hotkeyTagEdit);
    
    m_addHotkeyBtn = new QPushButton("Add", tab);
    m_addHotkeyBtn->setObjectName("smallBtn");
    hotkeyAddLayout->addWidget(m_addHotkeyBtn);
    layout->addLayout(hotkeyAddLayout);
    
    connect(m_addHotkeyBtn, &QPushButton::clicked, this, &Sidebar::onAddHotkeyClicked);
    
    // Hotkey list
    QScrollArea* hotkeyScroll = new QScrollArea(tab);
    hotkeyScroll->setWidgetResizable(true);
    hotkeyScroll->setMaximumHeight(150);
    hotkeyScroll->setFrameShape(QFrame::NoFrame);
    
    m_hotkeyListWidget = new QWidget();
    m_hotkeyListLayout = new QVBoxLayout(m_hotkeyListWidget);
    m_hotkeyListLayout->setContentsMargins(0, 0, 0, 0);
    m_hotkeyListLayout->setSpacing(4);
    m_hotkeyListLayout->addStretch();
    hotkeyScroll->setWidget(m_hotkeyListWidget);
    layout->addWidget(hotkeyScroll);
    
    rebuildHotkeyList();
    
    // Separator
    QFrame* sep1 = new QFrame(tab);
    sep1->setFrameShape(QFrame::HLine);
    sep1->setObjectName("separator");
    layout->addWidget(sep1);
    
    // Mode buttons
    m_viewingModeBtn = new QPushButton("Enter Viewing Mode", tab);
    m_viewingModeBtn->setCheckable(true);
    layout->addWidget(m_viewingModeBtn);
    connect(m_viewingModeBtn, &QPushButton::toggled, this, &Sidebar::viewingModeToggled);
    
    m_taggingModeBtn = new QPushButton("Enter Tagging Mode", tab);
    m_taggingModeBtn->setCheckable(true);
    layout->addWidget(m_taggingModeBtn);
    connect(m_taggingModeBtn, &QPushButton::toggled, this, &Sidebar::taggingModeToggled);
    
    // Separator
    QFrame* sep2 = new QFrame(tab);
    sep2->setFrameShape(QFrame::HLine);
    sep2->setObjectName("separator");
    layout->addWidget(sep2);
    
    // Tag filters
    QLabel* tagTitle = new QLabel("Filter by Tags", tab);
    tagTitle->setObjectName("sectionTitle");
    layout->addWidget(tagTitle);
    
    // Untagged checkbox
    m_untaggedCheckbox = new QCheckBox("Show Untagged Only", tab);
    layout->addWidget(m_untaggedCheckbox);
    connect(m_untaggedCheckbox, &QCheckBox::toggled, this, &Sidebar::onUntaggedToggled);
    
    // Tag list scroll area
    QScrollArea* tagScroll = new QScrollArea(tab);
    tagScroll->setWidgetResizable(true);
    tagScroll->setFrameShape(QFrame::NoFrame);
    
    m_tagListWidget = new QWidget();
    m_tagListLayout = new QVBoxLayout(m_tagListWidget);
    m_tagListLayout->setContentsMargins(0, 0, 0, 0);
    m_tagListLayout->setSpacing(2);
    m_tagListLayout->addStretch();
    tagScroll->setWidget(m_tagListWidget);
    layout->addWidget(tagScroll, 1);
    
    rebuildTagList();
}

void Sidebar::setDarkMode(bool dark) {
    m_darkMode = dark;
    applyTheme();
}

void Sidebar::applyTheme() {
    QString styleSheet;
    
    if (m_darkMode) {
        styleSheet = R"(
            Sidebar {
                background-color: #111827;
            }
            QLabel {
                color: #f3f4f6;
            }
            QLabel#titleLabel {
                color: #f3f4f6;
            }
            QLabel#mutedLabel {
                color: #9ca3af;
            }
            QLabel#sectionTitle {
                color: #f3f4f6;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 6px;
                color: #f3f4f6;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QPushButton {
                background-color: #374151;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:pressed, QPushButton:checked {
                background-color: #3b82f6;
            }
            QPushButton#pickFolderBtn {
                background-color: #4c1d95;
            }
            QPushButton#pickFolderBtn:hover {
                background-color: #5b21b6;
            }
            QPushButton#scanFolderBtn {
                background-color: #6d28d9;
            }
            QPushButton#scanFolderBtn:hover {
                background-color: #7c3aed;
            }
            QPushButton#smallBtn {
                padding: 4px 8px;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                background: #020617;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1f2937;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #374151;
            }
            QCheckBox {
                color: #f3f4f6;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #374151;
                border-radius: 4px;
                background: #1f2937;
            }
            QCheckBox::indicator:checked {
                background: #3b82f6;
                border-color: #3b82f6;
            }
            QFrame#separator {
                background-color: #374151;
                max-height: 1px;
            }
            QTabWidget::pane {
                border: none;
                background-color: transparent;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #9ca3af;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #4c1d95;
                color: #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #1f2937;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        )";
    } else {
        styleSheet = R"(
            Sidebar {
                background-color: #ffffff;
            }
            QLabel {
                color: #111827;
            }
            QLabel#mutedLabel {
                color: #6b7280;
            }
            QLabel#sectionTitle {
                color: #111827;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px;
                color: #111827;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
            QPushButton {
                background-color: #e5e7eb;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #111827;
            }
            QPushButton:hover {
                background-color: #d1d5db;
            }
            QPushButton:pressed, QPushButton:checked {
                background-color: #2563eb;
                color: #ffffff;
            }
            QPushButton#pickFolderBtn {
                background-color: #4c1d95;
                color: #ffffff;
            }
            QPushButton#scanFolderBtn {
                background-color: #6d28d9;
                color: #ffffff;
            }
            QSlider::groove:horizontal {
                background: #e5e7eb;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #9ca3af;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QCheckBox {
                color: #111827;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #d1d5db;
                border-radius: 4px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
            }
            QFrame#separator {
                background-color: #e5e7eb;
                max-height: 1px;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #6b7280;
                padding: 8px 16px;
            }
            QTabBar::tab:selected {
                background-color: #9a3412;
                color: #ffffff;
            }
        )";
    }
    
    setStyleSheet(styleSheet);
}

void Sidebar::refreshTags() {
    rebuildTagList();
}

QString Sidebar::currentFolder() const {
    return m_folderEdit->text();
}

void Sidebar::setCurrentFolder(const QString& path) {
    m_folderEdit->setText(path);
}

int Sidebar::thumbnailSize() const {
    return m_thumbSlider->value();
}

QSet<QString> Sidebar::selectedFilterTags() const {
    return m_selectedTags;
}

bool Sidebar::showUntaggedOnly() const {
    return m_showUntagged;
}

void Sidebar::onThumbnailSliderChanged(int value) {
    m_thumbSizeLabel->setText(QString::number(value) + "px");
    Config::instance().setThumbnailSize(value);
    emit thumbnailSizeChanged(value);
}

void Sidebar::onTagCheckboxToggled(bool checked) {
    QCheckBox* checkbox = qobject_cast<QCheckBox*>(sender());
    if (!checkbox) return;
    
    QString tagName = checkbox->property("tagName").toString();
    
    if (checked) {
        m_selectedTags.insert(tagName);
    } else {
        m_selectedTags.remove(tagName);
    }
    
    emit filterChanged();
}

void Sidebar::onUntaggedToggled(bool checked) {
    m_showUntagged = checked;
    emit filterChanged();
}

void Sidebar::onAddHotkeyClicked() {
    QString key = m_hotkeyKeyEdit->text().trimmed().toLower();
    QString tag = m_hotkeyTagEdit->text().trimmed().toLower();
    
    if (key.isEmpty() || tag.isEmpty()) return;
    
    Config::instance().setHotkey(key, tag);
    Config::instance().save();
    
    m_hotkeyKeyEdit->clear();
    m_hotkeyTagEdit->clear();
    
    rebuildHotkeyList();
    emit hotkeyAdded(key, tag);
}

void Sidebar::onRemoveHotkeyClicked() {
    QPushButton* btn = qobject_cast<QPushButton*>(sender());
    if (!btn) return;
    
    QString key = btn->property("hotkeyKey").toString();
    Config::instance().removeHotkey(key);
    Config::instance().save();
    
    rebuildHotkeyList();
    emit hotkeyRemoved(key);
}

void Sidebar::rebuildHotkeyList() {
    // Clear existing widgets
    QLayoutItem* item;
    while ((item = m_hotkeyListLayout->takeAt(0)) != nullptr) {
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
    
    auto hotkeys = Config::instance().hotkeys();
    
    for (auto it = hotkeys.begin(); it != hotkeys.end(); ++it) {
        QWidget* row = new QWidget();
        QHBoxLayout* rowLayout = new QHBoxLayout(row);
        rowLayout->setContentsMargins(0, 0, 0, 0);
        rowLayout->setSpacing(4);
        
        QLabel* keyLabel = new QLabel(QString("[%1]").arg(it.key()));
        keyLabel->setObjectName("hotkeyKey");
        keyLabel->setStyleSheet("color: #fbbf24; font-weight: bold;");
        rowLayout->addWidget(keyLabel);
        
        QLabel* tagLabel = new QLabel(it.value());
        tagLabel->setStyleSheet(m_darkMode ? "color: #f3f4f6;" : "color: #111827;");
        rowLayout->addWidget(tagLabel, 1);
        
        QPushButton* removeBtn = new QPushButton("×");
        removeBtn->setObjectName("smallBtn");
        removeBtn->setFixedSize(20, 20);
        removeBtn->setProperty("hotkeyKey", it.key());
        connect(removeBtn, &QPushButton::clicked, this, &Sidebar::onRemoveHotkeyClicked);
        rowLayout->addWidget(removeBtn);
        
        m_hotkeyListLayout->insertWidget(m_hotkeyListLayout->count() - 1, row);
    }
}

void Sidebar::rebuildTagList() {
    // Clear existing checkboxes
    for (auto* checkbox : m_tagCheckboxes) {
        m_tagListLayout->removeWidget(checkbox);
        delete checkbox;
    }
    m_tagCheckboxes.clear();
    
    auto tagCounts = m_db->tagCounts();
    
    for (const auto& pair : tagCounts) {
        QString tagName = pair.first;
        int count = pair.second;
        
        QCheckBox* checkbox = new QCheckBox(QString("%1 (%2)").arg(tagName).arg(count));
        checkbox->setProperty("tagName", tagName);
        checkbox->setChecked(m_selectedTags.contains(tagName));
        connect(checkbox, &QCheckBox::toggled, this, &Sidebar::onTagCheckboxToggled);
        
        m_tagListLayout->insertWidget(m_tagListLayout->count() - 1, checkbox);
        m_tagCheckboxes[tagName] = checkbox;
    }
    
    // Update untagged count
    int untaggedCount = m_db->untaggedCount();
    m_untaggedCheckbox->setText(QString("Show Untagged Only (%1)").arg(untaggedCount));
}

} // namespace KeyTagger

