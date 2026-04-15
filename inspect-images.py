#!/usr/bin/env python3
import toml
import asyncio


def get_images_to_inspect() -> list[str]:
    # exclude some images without a latest tag or are not accessible without a login
    return [
        url
        for shortname, url in toml.load("shortnames.conf")["aliases"].items()
        if shortname
        not in (
            "almalinux-minimal",
            "rockylinux",
            "rhel7/rhel-atomic",
            "rhel-minimal",
            "rhel7-minimal",
            "leap-dnf",
            "leap-microdnf",
            "rhel9-bootc",
        )
    ]


async def inspect_image(url: str) -> tuple[str, str] | None:
    proc = await asyncio.create_subprocess_shell(
        f"skopeo inspect --override-arch amd64 docker://{url}",
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    _, stderr = (out.decode() for out in await proc.communicate())
    if proc.returncode != 0:
        return url, stderr.strip()
    return None


if __name__ == "__main__":

    import argparse
    import os
    import pathlib
    import shutil

    parser = argparse.ArgumentParser(
        description="""Copies the shortnames.conf to
        ~/.config/containers/registries.conf.d or
        /etc/containers/registries.conf.d/ and try to inspect all images in the
        toml file."""
    )
    parser.add_argument(
        "--system-wide",
        action="store_true",
        help="copy shortnames.conf to /etc/containers/registries.conf.d/ instead of into $HOME",
    )

    args = parser.parse_args()

    shortnames_dest = (
        "/etc/containers/registries.conf.d/000-shortnames.conf"
        if args.system_wide
        else os.path.expanduser(
            "~/.config/containers/registries.conf.d/000-shortnames.conf"
        )
    )

    pathlib.Path(os.path.dirname(shortnames_dest)).mkdir(exist_ok=True, parents=True)
    restore_old_shortnames = os.path.exists(shortnames_dest)
    if restore_old_shortnames:
        shutil.copy(shortnames_dest, f"{shortnames_dest}.back")
    shutil.copy("shortnames.conf", shortnames_dest)

    async def run():
        results = await asyncio.gather(
            *[inspect_image(url) for url in get_images_to_inspect()]
        )
        failures = [r for r in results if r is not None]
        if failures:
            print("Failed to inspect the following images:")
            for url, err in failures:
                print(f"  {url}\n    {err}")
            raise SystemExit(1)

    try:
        asyncio.run(run())

    finally:
        os.remove(shortnames_dest)
        if restore_old_shortnames:
            shutil.move(f"{shortnames_dest}.back", shortnames_dest)
