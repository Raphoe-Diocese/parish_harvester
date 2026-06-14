const PH_DEFAULT_GH_REPO = "Raphoe-Diocese/parish_harvester";

function phResolveGhRepo(storedRepo) {
  const value = String(storedRepo || "").trim();
  return value || PH_DEFAULT_GH_REPO;
}
