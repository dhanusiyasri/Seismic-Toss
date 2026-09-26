"""Compatibility entry point.

The original prototype trained an Isolation Forest here. The active demo model
is now the portable calibrated model in train_calibrated_model.py.
"""
from .train_calibrated_model import main

if __name__ == "__main__":
    main()
