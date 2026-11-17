"""Rigor evaluation package (single-instance module aliasing across eval.rigor / rigor)."""
import sys

if __name__ == "eval.rigor":
    sys.modules.setdefault("rigor", sys.modules[__name__])
elif __name__ == "rigor":
    try:
        import eval as _eval_pkg

        sys.modules.setdefault("eval.rigor", sys.modules[__name__])
        setattr(_eval_pkg, "rigor", sys.modules[__name__])
    except ImportError:
        pass
