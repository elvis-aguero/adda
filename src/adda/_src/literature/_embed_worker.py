"""Out-of-process embedding worker (bge-small via fastembed).

Runs in an ephemeral uv environment resolved with numpy<2 so that
onnxruntime's Intel-macOS wheels (NumPy-1.x builds) can load even
when the host project pins numpy>=2.

Protocol: read JSON {"texts": [...]} on stdin, write JSON
{"vectors": [[...], ...]} on stdout. Errors → nonzero exit with the
message on stderr.
"""
import json
import os
import sys


def _thread_count() -> int:
    """How many threads onnxruntime may use, per the CPUs we actually own.

    onnxruntime pins its worker threads to CPU indices when it is left to
    decide the thread count itself, and it derives those indices from the
    machine's CPU count rather than from the set the cgroup granted us. Under
    Slurm — every cluster run — those are different, so pthread_setaffinity_np
    is handed an index outside the allowed mask and fails with EINVAL. Its own
    error message names the remedy: "Specify the number of threads explicitly
    so the affinity is not set."

    sched_getaffinity is the cgroup-aware count and exists on Linux only;
    elsewhere the affinity problem does not arise and cpu_count is fine.
    """
    env = os.environ.get("OMP_NUM_THREADS")
    if env and env.strip().isdigit() and int(env) > 0:
        return int(env)
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return max(1, os.cpu_count() or 1)


def main() -> int:
    payload = json.load(sys.stdin)
    texts = payload["texts"]
    from fastembed import TextEmbedding
    model = TextEmbedding("BAAI/bge-small-en-v1.5", threads=_thread_count())
    vectors = [[float(x) for x in v] for v in model.embed(texts)]
    json.dump({"vectors": vectors}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
