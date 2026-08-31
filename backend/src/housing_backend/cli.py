from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from housing_backend.bootstrap import Container
from housing_backend.infrastructure.http import safe_error


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="주택청약 데이터 수집/관리 CLI")
    commands = root.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="공식 API에서 신규/변경 공고 수집")
    collect.add_argument("--sources", default="applyhome,lh")
    collect.add_argument("--since", type=date.fromisoformat)
    collect.add_argument("--until", type=date.fromisoformat)

    loop = commands.add_parser("collect-loop", help="지정 간격으로 공식 API 수집 반복")
    loop.add_argument("--sources", default="applyhome,lh")
    loop.add_argument("--since", type=date.fromisoformat)
    loop.add_argument("--until", type=date.fromisoformat)
    loop.add_argument("--interval-seconds", type=int, default=1800)

    seed = commands.add_parser("seed-regions", help="지도 GeoJSON에서 행정구역 적재")
    seed.add_argument("--geojson", default="../assets/sgg.json")
    return root


async def run(args: argparse.Namespace) -> None:
    container = Container()
    await container.startup()
    try:
        if args.command in {"collect", "collect-loop"}:
            if not container.settings.has_service_key:
                raise SystemExit("DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")
            names = [name.strip() for name in args.sources.split(",") if name.strip()]
            unknown = sorted(set(names) - set(container.sources))
            if unknown:
                raise SystemExit(f"알 수 없는 소스: {', '.join(unknown)}")
            while True:
                try:
                    results = await container.collect_notices.execute(
                        names, since=args.since, until=args.until
                    )
                    print(
                        json.dumps(
                            [asdict(result) for result in results],
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                except Exception as exc:
                    print(json.dumps({"status": "failed", "error": safe_error(exc)}))
                    if args.command == "collect":
                        raise
                if args.command == "collect":
                    break
                await asyncio.sleep(max(args.interval_seconds, 60))
        elif args.command == "seed-regions":
            records = _region_records(Path(args.geojson))
            created = await container.repository.seed_regions(records)
            print(f"regions: {len(records)} total, {created} created")
    finally:
        await container.shutdown()


def _region_records(path: Path) -> list[dict[str, str | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    provinces: dict[str, str] = {}
    districts: dict[str, tuple[str, str]] = {}
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        province_code = str(props.get("sido", ""))
        district_code = str(props.get("sgg", ""))
        province_name = str(props.get("sidonm", ""))
        district_name = str(props.get("sggnm", ""))
        if province_code and province_name:
            provinces[province_code] = province_name
        if district_code and district_name:
            districts[district_code] = (district_name, province_code)
    rows = [
        {"code": code, "name": name, "level": "province", "parent_code": None}
        for code, name in sorted(provinces.items())
    ]
    rows.extend(
        {
            "code": code,
            "name": name,
            "level": "district",
            "parent_code": parent,
        }
        for code, (name, parent) in sorted(districts.items())
    )
    return rows


def main() -> None:
    asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    main()
