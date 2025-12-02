#include <QApplication>
#include <QDir>
#include <QFile>
#include <QTextStream>
#include <QDateTime>
#include <QMessageBox>

#include "MainWindow.h"
#include "Config.h"

void messageHandler(QtMsgType type, const QMessageLogContext& context, const QString& msg) {
    Q_UNUSED(context);
    
    static QFile logFile("keytagger_crash.log");
    static bool fileOpened = false;
    
    if (!fileOpened) {
        logFile.open(QIODevice::WriteOnly | QIODevice::Append);
        fileOpened = true;
    }
    
    QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");
    QString levelStr;
    
    switch (type) {
        case QtDebugMsg: levelStr = "DEBUG"; break;
        case QtInfoMsg: levelStr = "INFO"; break;
        case QtWarningMsg: levelStr = "WARNING"; break;
        case QtCriticalMsg: levelStr = "CRITICAL"; break;
        case QtFatalMsg: levelStr = "FATAL"; break;
    }
    
    QString logLine = QString("[%1] %2: %3\n").arg(timestamp, levelStr, msg);
    
    QTextStream stream(&logFile);
    stream << logLine;
    stream.flush();
    
    // Also output to stderr
    QTextStream(stderr) << logLine;
    
    if (type == QtFatalMsg) {
        abort();
    }
}

int main(int argc, char* argv[]) {
    // Set up logging
    qInstallMessageHandler(messageHandler);
    
    // High DPI support
    QApplication::setHighDpiScaleFactorRoundingPolicy(
        Qt::HighDpiScaleFactorRoundingPolicy::PassThrough);
    
    QApplication app(argc, argv);
    app.setApplicationName("KeyTagger");
    app.setApplicationVersion("1.0.0");
    app.setOrganizationName("KeyTagger");
    
    // Set working directory to application directory
    QDir::setCurrent(app.applicationDirPath());
    
    // For development, use the source directory
    if (!QFile::exists("keytag_config.json")) {
        QString sourceDir = QDir::currentPath();
        if (QFile::exists(sourceDir + "/../keytag_config.json")) {
            QDir::setCurrent(sourceDir + "/..");
        }
    }
    
    // Initialize configuration
    KeyTagger::Config::instance().setConfigPath("keytag_config.json");
    KeyTagger::Config::instance().load();
    
    try {
        KeyTagger::MainWindow mainWindow;
        mainWindow.show();
        
        return app.exec();
    } catch (const std::exception& e) {
        QMessageBox::critical(nullptr, "Fatal Error",
            QString("An unrecoverable error occurred:\n\n%1").arg(e.what()));
        return 1;
    }
}

