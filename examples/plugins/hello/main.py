"""A standard-library-only text plugin. MIT, SeedBank contributors."""


def handle(request):
    lines = [line.strip() for line in request["input"].splitlines() if line.strip()]
    prefix = request["settings"].get("prefix", "今天的小事")
    return {"text": prefix + "\n" + "\n".join("• " + line for line in lines)}
