"""Quick test: re-run the pipeline on the existing transcript to compare output quality."""
import sys, os
sys.path.insert(0, r"D:\錄音檔\meeting-auto")
os.chdir(r"D:\錄音檔\meeting-auto")

from core import pipeline
pipeline.run(file_path=r"D:\錄音檔\meeting-auto\test\c1206bd9c32d06c80b82f4c449bea90f.txt")
