import os
import sys
import glob
from datetime import datetime
from logging_config import LoggingConfig


def show_log_status():
    """Отобразить статус логов"""
    print("📊 Статус файлов логов")
    print("=" * 50)
    
    info = LoggingConfig.get_log_files_info()
    
    for log_name, details in info.items():
        print("\n📝 {}:".format(log_name.replace('_', ' ').title()))
        print("   Путь: {}".format(details['path']))
        print("   Размер: {} MB".format(details['size_mb']))
        print("   Последнее изменение: {}".format(details['modified']))
    
    print("\n📁 Директория логов: {}".format(LoggingConfig.LOG_DIR))
    print("   Директория существует: {}".format(os.path.exists(LoggingConfig.LOG_DIR)))
    
    if os.path.exists(LoggingConfig.LOG_DIR):
        log_files = glob.glob(os.path.join(LoggingConfig.LOG_DIR, "*.log*"))
        print("   Всего файлов лога: {}".format(len(log_files)))
        
        total_size = sum(os.path.getsize(f) for f in log_files if os.path.isfile(f))
        print("   Общий размер: {:.2f} MB".format(total_size / (1024*1024)))


def tail_log(lines=20):
    """Показать последние N строк лога"""
    log_file = LoggingConfig.LOG_FILE
    
    if not os.path.exists(log_file):
        print("❌ Файл лога не существует: {}".format(log_file))
        return
    
    print("📄 Последние {} строк лога:".format(lines))
    print("=" * 60)
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            for line in last_lines:
                print(line.rstrip())
                
    except Exception as e:
        print("❌ Ошибка чтения файла лога: {}".format(e))


def clear_logs():
    """Очистить файл лога"""
    log_file = LoggingConfig.LOG_FILE
    
    cleared_count = 0
    
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
            print("✅ Очищено: {}".format(os.path.basename(log_file)))
            cleared_count += 1
        except Exception as e:
            print("❌ Ошибка очистки {}: {}".format(os.path.basename(log_file), e))
    
    # Clear rotated log files
    if os.path.exists(LoggingConfig.LOG_DIR):
        rotated_files = glob.glob(os.path.join(LoggingConfig.LOG_DIR, "*.log.*"))
        for rot_file in rotated_files:
            try:
                os.remove(rot_file)
                print("✅ Очищено: {}".format(os.path.basename(rot_file)))
                cleared_count += 1
            except Exception as e:
                print("❌ Ошибка очистки {}: {}".format(os.path.basename(rot_file), e))
    
    print("\n📊 Всего очищено: {}".format(cleared_count))


def main():
    """Основной CLI интерфейс"""
    if len(sys.argv) < 2:
        print("📝 News Analyzer - Утилиты для работы с логами")
        print("\nКоманды:")
        print("  python log_utils.py status         - Показать статус файла лога")
        print("  python log_utils.py tail N   - Показать последние N строк лога")
        print("  python log_utils.py clear          - Очистить файл лога")
        print("\nПример: python log_utils.py tail 50")
        return
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_log_status()
        
    elif command == "tail":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        tail_log(lines)
        
    elif command == "clear":
        confirm = input("⚠️  Вы уверены, что хотите очистить файл лога? (y/N): ")
        if confirm.lower() == 'y':
            clear_logs()
        else:
            print("❌ Операция отменена")
            
    else:
        print("❌ Неизвестная команда: {}".format(command))


if __name__ == "__main__":
    main()
