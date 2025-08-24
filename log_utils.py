#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Log utilities for News Analyzer project
"""

import os
import sys
import glob
from datetime import datetime
from logging_config import LoggingConfig


def show_log_status():
    """Display current log files status"""
    print("📊 News Analyzer - Log Files Status")
    print("=" * 50)
    
    info = LoggingConfig.get_log_files_info()
    
    for log_name, details in info.items():
        print("\n📝 {}:".format(log_name.replace('_', ' ').title()))
        print("   Path: {}".format(details['path']))
        print("   Size: {} MB".format(details['size_mb']))
        print("   Last Modified: {}".format(details['modified']))
    
    print("\n📁 Log Directory: {}".format(LoggingConfig.LOG_DIR))
    print("   Directory exists: {}".format(os.path.exists(LoggingConfig.LOG_DIR)))
    
    if os.path.exists(LoggingConfig.LOG_DIR):
        log_files = glob.glob(os.path.join(LoggingConfig.LOG_DIR, "*.log*"))
        print("   Total log files: {}".format(len(log_files)))
        
        total_size = sum(os.path.getsize(f) for f in log_files if os.path.isfile(f))
        print("   Total size: {:.2f} MB".format(total_size / (1024*1024)))


def tail_log(lines=20):
    """Show last N lines of the log file"""
    log_file = LoggingConfig.LOG_FILE
    
    if not os.path.exists(log_file):
        print("❌ Log file does not exist: {}".format(log_file))
        return
    
    print("📄 Last {} lines of news_analyzer log:".format(lines))
    print("=" * 60)
    
    try:
        with open(log_file, 'r') as f:
            # Read all lines and get the last N
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            for line in last_lines:
                print(line.rstrip())
                
    except Exception as e:
        print("❌ Error reading log file: {}".format(e))


def clear_logs():
    """Clear the log file"""
    log_file = LoggingConfig.LOG_FILE
    
    cleared_count = 0
    
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
            print("✅ Cleared: {}".format(os.path.basename(log_file)))
            cleared_count += 1
        except Exception as e:
            print("❌ Error clearing {}: {}".format(os.path.basename(log_file), e))
    
    # Clear rotated log files
    if os.path.exists(LoggingConfig.LOG_DIR):
        rotated_files = glob.glob(os.path.join(LoggingConfig.LOG_DIR, "*.log.*"))
        for rot_file in rotated_files:
            try:
                os.remove(rot_file)
                print("✅ Cleared rotated: {}".format(os.path.basename(rot_file)))
                cleared_count += 1
            except Exception as e:
                print("❌ Error clearing {}: {}".format(os.path.basename(rot_file), e))
    
    print("\n📊 Total files cleared: {}".format(cleared_count))


def main():
    """Main CLI interface"""
    if len(sys.argv) < 2:
        print("📝 News Analyzer - Log Utilities")
        print("\nUsage:")
        print("  python log_utils.py status         - Show log file status")
        print("  python log_utils.py tail [lines]   - Show last lines of log")
        print("  python log_utils.py clear          - Clear log file")
        print("\nExample: python log_utils.py tail 50")
        return
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_log_status()
        
    elif command == "tail":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        tail_log(lines)
        
    elif command == "clear":
        confirm = input("⚠️  Are you sure you want to clear the log file? (y/N): ")
        if confirm.lower() == 'y':
            clear_logs()
        else:
            print("❌ Operation cancelled")
            
    else:
        print("❌ Unknown command: {}".format(command))


if __name__ == "__main__":
    main()
