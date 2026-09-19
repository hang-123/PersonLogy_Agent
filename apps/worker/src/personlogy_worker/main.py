"""Compatibility entrypoint for the shared worker."""

from personlogy.runtime.worker import main as main
from personlogy.runtime.worker import run_worker as run_worker

if __name__ == "__main__":
    main()
