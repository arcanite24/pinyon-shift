import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-dispatch.py"
SPEC = importlib.util.spec_from_file_location("native_dispatch_discovery", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture(address, body):
    return "\n".join(
        [
            "DEFINE_REX_FUNC(sub_{:08X}) {{".format(address),
            "\tREX_FUNC_PROLOGUE();",
            *[
                line if line.startswith("loc_") else "\t// {}".format(line)
                for line in body
            ],
            "}",
        ]
    )


def reviewed_fixtures(include_immediate=True):
    dirty_clears = []
    for offset in (16, 16, 16, 16, 24, 32):
        dirty_clears.extend(
            [
                f"ld r20,{offset}(r31)",
                "rldicr r20,r20,0,51",
                f"std r20,{offset}(r31)",
            ]
        )
    chunks = [
        fixture(
            0x824079B8,
            ["mflr r12", "loc_824079F8:", "bl 0x8240f4d8"],
        ),
        fixture(
            0x8240F4D8,
            [
                "mflr r12",
                "loc_82410318:",
                "oris r11,r11,49152",
                "rlwimi r10,r29,16,0,15",
                "ori r11,r11,13824",
                "cmpwi cr6,r22,0",
                "stwu r11,4(r3)",
                *dirty_clears,
            ],
        ),
        fixture(
            0x824587D8,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,17920",
                "stwu r20,4(r3)",
                "lis r21,-16383",
                "ori r21,r21,15616",
                "stwu r21,4(r3)",
                "lis r22,-16383",
                "ori r22,r22,15616",
                "stwu r22,4(r3)",
                "lis r23,-16380",
                "ori r23,r23,15360",
                "stwu r23,4(r3)",
                "lis r24,-16380",
                "ori r24,r24,15360",
                "stwu r24,4(r3)",
                "lis r25,-16383",
                "ori r25,r25,23040",
                "stwu r25,4(r3)",
                "bl 0x82458a88",
                "bl 0x82458a88",
            ],
        ),
        fixture(
            0x82458A88,
            [
                "mflr r12",
                "li r11,8712",
                "li r10,6",
                "stwu r11,4(r3)",
                "lis r11,1",
                "stwu r10,4(r3)",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
                "lis r22,-16384",
                "ori r22,r22,24576",
                "stwu r22,4(r3)",
                "lis r23,-16384",
                "ori r23,r23,24832",
                "stwu r23,4(r3)",
                "lis r24,-16384",
                "ori r24,r24,23296",
                "stwu r24,4(r3)",
            ],
        ),
        fixture(
            0x829F21A0,
            [
                "mflr r12",
                "lis r9,-16384",
                "ori r9,r9,8960",
                "stwu r9,4(r11)",
                "or r10,r9,r10",
                "std r10,12424(r31)",
            ],
        ),
        fixture(
            0x829F2280,
            [
                "mflr r12",
                "lis r11,-16384",
                "ori r11,r11,8960",
                "stwu r11,4(r3)",
                "andc r11,r10,r11",
                "std r11,12424(r31)",
            ],
        ),
        fixture(
            0x82D951E0,
            [
                "mflr r12",
                "bl 0x829f21a0",
                "bl 0x82415f68",
                "bl 0x829f2280",
            ],
        ),
        fixture(
            0x82413AB8,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
            ],
        ),
        fixture(
            0x824736F0,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
                "lis r22,-16384",
                "ori r22,r22,25088",
                "stwu r22,4(r3)",
                "lis r23,-16384",
                "ori r23,r23,25344",
                "stwu r23,4(r3)",
                "bl 0x82413ab8",
            ],
        ),
        fixture(0x82D95408, ["bl 0x82d951e0"]),
        fixture(0x82DA8CB0, ["bl 0x82d951e0"]),
        fixture(0x829ED510, ["b 0x82413ab8"]),
        fixture(0x8246FB90, ["bl 0x829ed510"]),
    ]
    if include_immediate:
        chunks.append(
            fixture(
                0x829F7C70,
                [
                    "mflr r12",
                    "loc_829F7CA0:",
                    "lis r11,-16384",
                    "rlwinm r10,r29,16,0,15",
                    "ori r11,r11,13824",
                    "or r10,r10,r30",
                    "stwu r11,4(r3)",
                ],
            )
        )
    return chunks


def owner_fixtures():
    return [
        fixture(
            0x82409668,
            [
                "mflr r12",
                "loc_82409834:",
                "bl 0x82409398",
                "mr r3,r29",
                "addi r1,r1,176",
                "b 0x82a7de40",
            ],
        ),
        fixture(
            0x824167F8,
            [
                "mflr r12",
                "loc_82416894:",
                "bl 0x82416a00",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x8246E8F8,
            [
                "mflr r12",
                "loc_8246E92C:",
                "bl 0x82416a00",
                "mr r3,r30",
                "bl 0x82467468",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x829F5FF0,
            [
                "mflr r12",
                "loc_829F6304:",
                "bl 0x82409398",
                "loc_829F6338:",
                "bl 0x82409398",
                "loc_829F6354:",
                "mr r3,r31",
                "addi r1,r1,176",
                "b 0x82a7de44",
            ],
        ),
    ]


def producer_fixtures():
    return [
        fixture(
            0x8240D070,
            [
                "mflr r12",
                "bl 0x82409668",
                "loc_8240D1F0:",
                "addi r1,r1,128",
                "b 0x82a7de58",
            ],
        ),
        fixture(
            0x82417060,
            [
                "mflr r12",
                "bl 0x824167f8",
                "loc_824170C0:",
                "addi r1,r1,96",
                "blr",
            ],
        ),
        fixture(
            0x829F6360,
            [
                "mflr r12",
                "bl 0x829f5ff0",
                "loc_829F63FC:",
                "addi r1,r1,128",
                "b 0x82a7de54",
            ],
        ),
    ]


def context_fixtures():
    return [
        fixture(
            0x8240CF68,
            [
                "mflr r12",
                "loc_8240CF80:",
                "mr r31,r3",
                "loc_8240CFF8:",
                "mr r3,r31",
                "bl 0x8240d070",
                "loc_8240D054:",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x82417BC0,
            [
                "mflr r12",
                "loc_82417BF0:",
                "stw r6,2156(r1)",
                "loc_82418058:",
                "lwz r8,2156(r1)",
                "loc_82418068:",
                "addis r24,r8,1",
                "loc_8241807C:",
                "addi r24,r24,-5824",
                "loc_82418A20:",
                "mr r3,r24",
                "bl 0x82417060",
                "loc_82418EC4:",
                "mr r3,r24",
                "bl 0x82417060",
                "loc_82418F38:",
                "addi r1,r1,2112",
                "b 0x82a7de20",
            ],
        ),
        fixture(
            0x824365B0,
            [
                "mflr r12",
                "loc_824365C0:",
                "mr r29,r3",
                "loc_8243667C:",
                "addis r25,r29,1",
                "loc_82436688:",
                "addi r25,r25,-5824",
                "loc_82436690:",
                "stw r25,84(r1)",
                "loc_82437030:",
                "lwz r25,84(r1)",
                "loc_82437040:",
                "mr r3,r25",
                "bl 0x82417060",
                "loc_82437048:",
                "addi r1,r1,1472",
                "b 0x82a7de20",
            ],
        ),
        fixture(
            0x829F6620,
            [
                "mflr r12",
                "loc_829F662C:",
                "mr r28,r3",
                "loc_829F67A8:",
                "mr r3,r28",
                "bl 0x829f6360",
                "loc_829F67B4:",
                "li r3,0",
                "loc_829F67B8:",
                "addi r1,r1,176",
                "b 0x82a7de44",
            ],
        ),
    ]


def procedural_model_lifecycle_fixtures():
    return [
        fixture(
            0x82E1C9A0,
            [
                "mflr r12",
                "loc_82E1C9B8:",
                "bl 0x82e19478",
                "loc_82E1C9BC:",
                "lis r11,-32256",
                "loc_82E1C9C4:",
                "addi r11,r11,11100",
                "loc_82E1C9D0:",
                "stw r11,0(r31)",
                "loc_82E1CA0C:",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x82E1CA28,
            [
                "mflr r12",
                "loc_82E1CA3C:",
                "lis r11,-32256",
                "loc_82E1CA48:",
                "addi r11,r11,11100",
                "loc_82E1CA50:",
                "stw r11,0(r3)",
                "loc_82E1CBCC:",
                "bl 0x82e1c0c0",
                "loc_82E1CBD0:",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x82E1D9B0,
            [
                "mflr r12",
                "loc_82E1D9CC:",
                "bl 0x82e1ca28",
                "blr",
            ],
        ),
        fixture(
            0x82E1CDC8,
            [
                "mflr r12",
                "loc_82E1CDD8:",
                "rlwinm r3,r3,9,0,22",
                "loc_82E1CDFC:",
                "bl 0x82e1c9a0",
                "loc_82E1CE04:",
                "addi r31,r31,512",
                "blr",
            ],
        ),
        fixture(
            0x82E1FD00,
            [
                "mflr r12",
                "loc_82E1FD20:",
                "mr r20,r3",
                "loc_82E1FD40:",
                "lwz r11,124(r3)",
                "loc_82E1FD4C:",
                "lwz r11,136(r3)",
                "loc_82E1FE10:",
                "lwz r11,128(r20)",
                "loc_82E1FEB8:",
                "lwz r9,128(r20)",
                "loc_82E1FEF0:",
                "lwz r8,732(r1)",
                "mulli r10,r15,192",
                "lwz r11,4(r20)",
                "loc_82E1FF0C:",
                "add r14,r10,r8",
                "loc_82E1FF20:",
                "lfs f12,160(r14)",
                "lfs f13,164(r14)",
                "lfs f11,168(r14)",
                "loc_82E1FF64:",
                "lwz r11,4(r20)",
                "loc_82E1FF80:",
                "lvx128 v63,r11,r9",
                "loc_82E1FF88:",
                "lvx128 v62,r11,r8",
                "loc_82E1FFA4:",
                "bgt cr6,0x82e20878",
                "loc_82E1FFAC:",
                "lwz r4,740(r1)",
                "loc_82E1FFDC:",
                "add r3,r11,r4",
                "loc_82E20024:",
                "bl 0x8243f9a0",
                "loc_82E2003C:",
                "bl 0x82441048",
                "loc_82E20048:",
                "lwz r11,124(r20)",
                "loc_82E2012C:",
                "lfs f0,44(r21)",
                "fmuls f0,f0,f0",
                "fcmpu cr6,f26,f0",
                "loc_82E201A0:",
                "lfs f0,60(r23)",
                "loc_82E201AC:",
                "fmuls f0,f0,f0",
                "fcmpu cr6,f26,f0",
                "loc_82E20258:",
                "fcmpu cr6,f0,f29",
                "loc_82E202D8:",
                "fcmpu cr6,f31,f0",
                "loc_82E2034C:",
                "bl 0x8243f9a0",
                "loc_82E20350:",
                "clrlwi. r11,r3,24",
                "loc_82E20364:",
                "bl 0x82441048",
                "loc_82E20368:",
                "cmpwi r3,0",
                "loc_82E20080:",
                "add r23,r11,r18",
                "loc_82E20090:",
                "add r21,r11,r17",
                "loc_82E205E4:",
                "stw r6,104(r25)",
                "loc_82E206DC:",
                "stw r6,104(r25)",
                "loc_82E206F4:",
                "lbz r11,18(r24)",
                "loc_82E206F8:",
                "cmplwi r11,0",
                "loc_82E2084C:",
                "lwz r11,124(r20)",
                "loc_82E20854:",
                "addi r18,r18,92",
                "loc_82E20858:",
                "addi r17,r17,68",
                "loc_82E208CC:",
                "addi r1,r1,704",
                "blr",
            ],
        ),
        fixture(
            0x8243F9A0,
            [
                "mflr r12",
                "loc_8243F9B0:",
                "lfs f13,20(r3)",
                "loc_8243F9CC:",
                "lvx128 v63,r0,r4",
                "lvx128 v62,r0,r5",
                "loc_8243F9DC:",
                "vsubfp128 v62,v62,v63",
                "loc_8243F9F8:",
                "vmsum3fp128 v62,v62,v62",
                "loc_8243FA04:",
                "lfs f1,96(r1)",
                "bl 0x8243fd70",
                "blr",
            ],
        ),
        fixture(
            0x8243FD70,
            [
                "lis r11,-32256",
                "lfs f13,20(r3)",
                "loc_8243FD8C:",
                "lvx128 v63,r0,r3",
                "loc_8243FD94:",
                "lvx128 v62,r0,r4",
                "vsubfp128 v63,v62,v63",
                "lfs f0,16(r3)",
                "lfs f13,24(r3)",
                "loc_8243FDAC:",
                "vmsum3fp128 v63,v63,v63",
                "loc_8243FDB8:",
                "fmuls f0,f0,f12",
                "fcmpu cr6,f0,f13",
                "blr",
            ],
        ),
        fixture(
            0x82441048,
            [
                "vor128 v62,v1,v1",
                "loc_8244105C:",
                "addi r11,r3,64",
                "loc_8244106C:",
                "addi r10,r3,80",
                "loc_82441074:",
                "addi r9,r3,48",
                "loc_8244107C:",
                "lvx128 v52,r0,r3",
                "loc_82441084:",
                "lvx128 v58,r0,r11",
                "loc_82441094:",
                "lvx128 v57,r0,r10",
                "loc_824410A0:",
                "addi r10,r3,32",
                "lvx128 v54,r0,r9",
                "loc_824410B0:",
                "lvx128 v45,r0,r11",
                "loc_824410C4:",
                "lvx128 v43,r0,r10",
                "loc_824412AC:",
                "li r3,0",
                "loc_824412C4:",
                "addi r3,r11,1",
                "blr",
            ],
        ),
        fixture(
            0x824170D8,
            [
                "mflr r12",
                "loc_824171AC:",
                "lwz r11,4(r30)",
                "loc_824171C0:",
                "lwz r3,0(r30)",
                "loc_824171D0:",
                "stw r11,84(r1)",
                "loc_824171D4:",
                "bl 0x82417418",
                "loc_824172F8:",
                "vmaddfp v1,v31,v0,v30",
                "loc_82417304:",
                "mr r3,r31",
                "loc_82417410:",
                "addi r1,r1,256",
                "blr",
            ],
        ),
        fixture(
            0x82410A58,
            [
                "lwz r11,0(r4)",
                "lwz r10,2812(r3)",
                "rlwinm r11,r11,2,0,29",
                "lwzx r3,r11,r10",
                "blr",
            ],
        ),
        fixture(
            0x82415AD0,
            [
                "mflr r12",
                "bl 0x82a7de08",
                "loc_82415AD8:",
                "stwu r1,-128(r1)",
                "li r10,5",
                "li r28,0",
                "mr r29,r5",
                "addi r11,r3,8",
                "mr r9,r28",
                "mr r31,r28",
                "mtctr r10",
                "loc_82415AF8:",
                "lwz r10,0(r11)",
                "lwz r8,-4(r11)",
                "addi r10,r10,1",
                "cmpw cr6,r8,r4",
                "stw r10,0(r11)",
                "bne cr6,0x82415b18",
                "addi r9,r11,-8",
                "b 0x82415b30",
                "loc_82415B18:",
                "cmplwi cr6,r31,0",
                "beq cr6,0x82415b2c",
                "lwz r8,8(r31)",
                "cmpw cr6,r10,r8",
                "ble cr6,0x82415b30",
                "loc_82415B2C:",
                "addi r31,r11,-8",
                "loc_82415B30:",
                "addi r11,r11,12",
                "bdnz 0x82415af8",
                "cmplwi cr6,r9,0",
                "beq cr6,0x82415b4c",
                "lwz r3,0(r9)",
                "stw r28,8(r9)",
                "b 0x82415bf0",
                "loc_82415B4C:",
                "stw r4,4(r31)",
                "mr r3,r29",
                "stw r4,80(r1)",
                "addi r4,r1,80",
                "stw r28,0(r31)",
                "bl 0x82410a58",
                "loc_82415B64:",
                "mr. r30,r3",
                "beq 0x82415be8",
                "lwz r11,0(r30)",
                "mr r3,r30",
                "lwz r11,24(r11)",
                "mtctr r11",
                "bctrl",
                "loc_82415B80:",
                "clrlwi. r11,r3,24",
                "lwz r11,0(r30)",
                "mr r3,r30",
                "beq 0x82415b98",
                "lwz r11,36(r11)",
                "b 0x82415bb8",
                "loc_82415B98:",
                "lwz r11,44(r11)",
                "mtctr r11",
                "bctrl",
                "loc_82415BA4:",
                "clrlwi. r11,r3,24",
                "beq 0x82415bc4",
                "lwz r11,0(r30)",
                "mr r3,r30",
                "lwz r11,40(r11)",
                "loc_82415BB8:",
                "mtctr r11",
                "bctrl",
                "loc_82415BC0:",
                "stw r3,0(r31)",
                "loc_82415BC4:",
                "lwz r11,0(r31)",
                "cmplwi cr6,r11,0",
                "bne cr6,0x82415be8",
                "lwz r11,8(r30)",
                "addis r3,r29,1",
                "addi r3,r3,-18544",
                "rlwinm r4,r11,19,13,31",
                "bl 0x823e58d8",
                "loc_82415BE4:",
                "stw r3,0(r31)",
                "loc_82415BE8:",
                "lwz r3,0(r31)",
                "stw r28,8(r31)",
                "loc_82415BF0:",
                "addi r1,r1,128",
                "b 0x82a7de58",
            ],
        ),
        fixture(
            0x82415BF8,
            [
                "mflr r12",
                "loc_82415C10:",
                "mr r31,r5",
                "loc_82415C14:",
                "cmpwi cr6,r4,0",
                "loc_82415C1C:",
                "cmpwi cr6,r5,5",
                "loc_82415C28:",
                "rlwinm r10,r5,2,0,29",
                "loc_82415C34:",
                "cmpw cr6,r9,r4",
                "loc_82415C3C:",
                "stwx r4,r10,r11",
                "loc_82415C44:",
                "mr r5,r6",
                "loc_82415C4C:",
                "bl 0x82415ad0",
                "loc_82415C50:",
                "mr. r5,r3",
                "loc_82415C54:",
                "beq 0x82415c70",
                "loc_82415C5C:",
                "mr r4,r31",
                "loc_82415C60:",
                "mr r3,r30",
                "loc_82415C64:",
                "lwz r11,88(r11)",
                "loc_82415C68:",
                "mtctr r11",
                "loc_82415C6C:",
                "bctrl",
                "blr",
            ],
        ),
        fixture(
            0x82417418,
            [
                "mflr r12",
                "loc_8241742C:",
                "mr r27,r3",
                "loc_82417494:",
                "addi r30,r27,448",
                "loc_824174D8:",
                "addi r30,r27,320",
                "loc_8241751C:",
                "addi r30,r27,384",
                "loc_82417668:",
                "lwz r10,124(r27)",
                "loc_8241766C:",
                "lwz r9,356(r1)",
                "loc_82417670:",
                "mulli r11,r9,92",
                "loc_82417674:",
                "lwz r10,0(r10)",
                "loc_824176AC:",
                "lwz r10,128(r27)",
                "loc_824176B0:",
                "mulli r11,r9,68",
                "loc_824176B8:",
                "add r26,r10,r11",
                "loc_824176C8:",
                "lwz r24,24(r26)",
                "loc_8241767C:",
                "lwz r8,36(r28)",
                "loc_82417680:",
                "cmplwi cr6,r8,4",
                "loc_82417688:",
                "cmplwi cr6,r8,5",
                "loc_82417694:",
                "li r11,1",
                "loc_8241769C:",
                "clrlwi r23,r11,24",
                "loc_824176D8:",
                "cmplwi cr6,r8,1",
                "loc_824176E0:",
                "cmplwi cr6,r8,3",
                "loc_824176EC:",
                "li r11,1",
                "loc_824176F4:",
                "clrlwi r21,r11,24",
                "loc_824176F8:",
                "cmpwi cr6,r25,9",
                "loc_82417704:",
                "cmpwi cr6,r25,11",
                "loc_8241770C:",
                "cmpwi cr6,r25,6",
                "loc_82417758:",
                "cmpwi cr6,r25,0",
                "loc_82417760:",
                "cmpwi cr6,r25,5",
                "loc_824177C4:",
                "lwz r22,28(r26)",
                "loc_824177C8:",
                "lwz r24,32(r26)",
                "loc_824177F8:",
                "lfs f13,40(r26)",
                "loc_82417870:",
                "lwz r11,36(r28)",
                "loc_82417890:",
                "cmpwi cr6,r25,9",
                "loc_824178C0:",
                "cmpwi cr6,r25,11",
                "loc_824178F0:",
                "cmpwi cr6,r25,24",
                "loc_824178F8:",
                "cmpwi cr6,r25,27",
                "loc_82417928:",
                "cmpwi cr6,r25,6",
                "loc_82417930:",
                "cmpwi cr6,r25,8",
                "loc_82417984:",
                "lwz r11,-14300(r30)",
                "loc_82417A58:",
                "lwz r11,0(r28)",
                "loc_82417A60:",
                "lwz r10,8(r27)",
                "loc_82417A64:",
                "li r5,0",
                "loc_82417A68:",
                "rlwinm r11,r11,3,0,28",
                "loc_82417A70:",
                "lwzx r4,r11,r10",
                "loc_82417A74:",
                "bl 0x82415bf8",
                "loc_82417A78:",
                "lwz r11,4(r28)",
                "loc_82417A80:",
                "blt cr6,0x82417aa0",
                "loc_82417A84:",
                "lwz r10,8(r27)",
                "loc_82417A88:",
                "rlwinm r11,r11,3,0,28",
                "loc_82417A90:",
                "li r5,1",
                "loc_82417A98:",
                "lwzx r4,r11,r10",
                "loc_82417A9C:",
                "bl 0x82415bf8",
                "loc_82417B44:",
                "lwz r11,0(r31)",
                "loc_82417B48:",
                "li r4,0",
                "loc_82417B50:",
                "lwz r5,0(r26)",
                "loc_82417B54:",
                "lwz r11,124(r11)",
                "loc_82417B5C:",
                "bctrl",
                "loc_82417B60:",
                "lwz r11,0(r31)",
                "loc_82417B64:",
                "mr r6,r24",
                "loc_82417B68:",
                "rlwinm r5,r22,2,0,29",
                "loc_82417B6C:",
                "li r4,13",
                "loc_82417B70:",
                "mr r3,r31",
                "loc_82417B74:",
                "lwz r11,160(r11)",
                "loc_82417B7C:",
                "bctrl",
                "loc_82417B80:",
                "addi r1,r1,272",
                "loc_82417B88:",
                "b 0x82a7de34",
            ],
        ),
        fixture(
            0x82415CE0,
            [
                "mflr r12",
                "loc_82415CFC:",
                "mr r31,r3",
                "loc_82415D00:",
                "lwz r3,20(r3)",
                "loc_82415D18:",
                "bl 0x82415f68",
                "loc_82415D1C:",
                "addi r11,r31,172",
                "blr",
            ],
        ),
        fixture(
            0x82415F68,
            [
                "mflr r12",
                "loc_82415F80:",
                "mr r31,r3",
                "loc_824161D4:",
                "lwz r3,48(r31)",
                "loc_82416250:",
                "lis r11,-16383",
                "loc_82416258:",
                "ori r11,r11,8705",
                "loc_82416260:",
                "stwu r11,4(r30)",
                "loc_824162C8:",
                "lis r9,-16383",
                "loc_824162D0:",
                "ori r9,r9,8705",
                "loc_824162F4:",
                "stwu r9,4(r6)",
                "loc_82416350:",
                "stw r11,48(r31)",
                "loc_82416370:",
                "b 0x824161d4",
                "blr",
            ],
        ),
    ]


def procedural_model_image():
    decorated = b".?AVCProceduralModels@proceduralGeometry@@\0"
    image = bytearray(0x12B9EE4 + len(decorated))

    def store(address, value):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + 4] = value.to_bytes(4, "big")

    store(0x82002B58, 0x82363C9C)
    store(0x82002B5C, 0x82E1D9B0)
    store(0x82002B94, 0x82E1FD00)
    store(0x82002BFC, 0x824170D8)
    store(0x82002C00, 0x82417BC0)
    store(0x82363CA8, 0x832B9EDC)
    name_offset = 0x832B9EDC - MODULE.IMAGE_BASE + 8
    image[name_offset : name_offset + len(decorated)] = decorated
    return bytes(image)


class NativeRendererDispatchDiscoveryTests(unittest.TestCase):
    def build(self, chunks, image=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pinyon_shift_recomp.1.cpp"
            path.write_text("\n\n".join(chunks), encoding="utf-8")
            return MODULE.build([path], image)

    def test_finds_reviewed_wrappers_and_direct_calls(self):
        caller = fixture(
            0x82B00000,
            [
                "bl 0x824079b8",
                "bl 0x8240f4d8",
                "bl 0x829f21a0",
                "bl 0x829f2280",
                "bl 0x829f7c70",
                "bl 0x82413ab8",
                "bl 0x824736f0",
            ],
        )
        document = self.build([*reviewed_fixtures(), caller])
        self.assertEqual(document["totals"]["reviewed_wrappers"], 10)
        self.assertEqual(document["totals"]["direct_calls"], 15)
        self.assertEqual(document["totals"]["tail_forwarded_calls"], 1)
        self.assertEqual(document["totals"]["runtime_correlation_calls"], 16)
        self.assertEqual(document["totals"]["adapter_argument_leads"], 1)
        self.assertEqual(document["totals"]["dirty_state_clears"], 6)
        self.assertEqual(document["totals"]["query_state_transitions"], 2)
        indexed_packet = next(
            item
            for item in document["packet_constructors"]
            if item["function_address"] == "8240F4D8"
            and item["opcode"] == "PM4_DRAW_INDX_2"
        )
        self.assertEqual(indexed_packet["header_source"], "dynamic_type3_count")
        provenance = document["draw_packet_provenance"]
        self.assertEqual(
            provenance["correlation"], "exact_physical_pm4_header_address"
        )
        self.assertEqual(
            [item["packet_hook_address"] for item in provenance["packet_sites"]],
            ["82410328", "829F7CB0"],
        )
        self.assertEqual(
            provenance["adapter_forward_return_address"], "824079FC"
        )
        adapter_call = next(
            item
            for item in document["direct_calls"]
            if item["wrapper_kind"] == "draw_adapter"
        )
        self.assertEqual(adapter_call["return_address"], "82B00004")
        self.assertEqual(
            document["resolve_boundary"]["classification"],
            "title_resolve_setup_and_backend_copy_proved",
        )
        self.assertEqual(document["totals"]["resolve_mode_writes"], 1)
        self.assertEqual(document["totals"]["query_owner_callers"], 2)
        self.assertEqual(
            document["query_owner_lifecycle"]["classification"],
            "query_lifecycle_owner_proved_semantics_unknown",
        )
        self.assertEqual(
            len(document["side_effect_packets"]["resolve_controller"]), 6
        )
        forwarded = document["tail_forwarded_calls"][0]
        self.assertEqual(forwarded["wrapper"], "82413AB8")
        self.assertEqual(forwarded["return_address"], "8246FB94")
        self.assertEqual(forwarded["forwarder_function"], "sub_829ED510")
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_adapter_argument_leads_stop_at_calls_and_decode_loads(self):
        caller = fixture(
            0x82B00000,
            [
                "bl 0x82415f68",
                "lwz r3,40(r31)",
                "mr r4,r30",
                "bl 0x824079b8",
            ],
        )
        document = self.build([*reviewed_fixtures(), caller])
        lead = document["adapter_argument_leads"][0]
        by_register = {item["register"]: item for item in lead["arguments"]}
        self.assertEqual(
            by_register["r3"]["status"], "bounded_syntactic_definition"
        )
        self.assertEqual(
            by_register["r3"]["memory_load"],
            {"base_register": "r31", "offset": 40, "width": "lwz"},
        )
        self.assertEqual(by_register["r4"]["source_registers"], ["r30"])
        self.assertEqual(
            by_register["r5"]["status"], "unknown_across_call_boundary"
        )
        self.assertFalse(lead["object_identity_proved"])
        self.assertFalse(lead["lifetime_proved"])

    def test_rejects_missing_reviewed_packet_evidence(self):
        incomplete = reviewed_fixtures(include_immediate=False)
        with self.assertRaisesRegex(ValueError, "829F7C70"):
            self.build(incomplete)

    def test_ignores_matching_numeric_work_without_a_packet_store(self):
        false_positive = fixture(
            0x83051E48,
            ["ori r12,r12,13824", "add r11,r11,r12"],
        )
        document = self.build([false_positive, *reviewed_fixtures()])
        addresses = {
            item["function_address"] for item in document["packet_constructors"]
        }
        self.assertNotIn("83051E48", addresses)

    def test_inventories_stored_indirect_buffer_packets(self):
        indirect = fixture(
            0x83060000,
            [
                "lis r11,-16382",
                "ori r11,r11,16128",
                "stwu r11,4(r3)",
                "lis r10,-16382",
                "ori r10,r10,14080",
                "stw r10,16(r4)",
            ],
        )
        caller = fixture(0x83070000, ["bl 0x83060000"])
        document = self.build([indirect, caller, *reviewed_fixtures()])
        packets = [
            item
            for item in document["packet_constructors"]
            if item["function_address"] == "83060000"
        ]
        self.assertEqual(
            [item["opcode"] for item in packets],
            ["PM4_INDIRECT_BUFFER", "PM4_INDIRECT_BUFFER_PFD"],
        )
        self.assertEqual(
            [item["header_source"] for item in packets],
            ["fixed_type3_count_3", "fixed_type3_count_3"],
        )
        self.assertEqual(packets[0]["packet_register"], "r11")
        self.assertEqual(packets[0]["store_instruction"], "stwu r11,4(r3)")
        self.assertEqual(document["totals"]["indirect_constructor_calls"], 1)
        constructor_call = document["indirect_constructor_calls"][0]
        self.assertEqual(
            constructor_call["constructor_function_address"], "83060000"
        )
        self.assertEqual(constructor_call["callsite"], "83070000")
        self.assertEqual(constructor_call["return_address"], "83070004")
        self.assertEqual(
            constructor_call["constructor_store_addresses"],
            ["83060008", "83060014"],
        )
        self.assertFalse(constructor_call["suppression_eligible"])

    def test_inventories_balanced_constructor_owner_layer(self):
        callers = [
            fixture(0x83010000, ["lwz r3,40(r31)", "bl 0x82409668"]),
            fixture(0x83020000, ["bl 0x824167f8"]),
            fixture(0x83030000, ["bl 0x8246e8f8"]),
            fixture(0x83040000, ["bl 0x829f5ff0"]),
        ]
        document = self.build(
            [*reviewed_fixtures(), *owner_fixtures(), *callers]
        )
        self.assertEqual(4, document["totals"]["indirect_owner_runtime_hooks"])
        self.assertEqual(4, document["totals"]["indirect_owner_calls"])
        self.assertEqual(4, document["totals"]["indirect_owner_argument_leads"])
        hooks = {
            item["function_address"]: item
            for item in document["indirect_owner_runtime_hooks"]
        }
        self.assertEqual("8240983C", hooks["82409668"]["exit_hook_address"])
        call = next(
            item
            for item in document["indirect_owner_calls"]
            if item["owner_function_address"] == "82409668"
        )
        self.assertEqual("83010004", call["callsite"])
        lead = next(
            item
            for item in document["indirect_owner_argument_leads"]
            if item["owner_function_address"] == "82409668"
        )
        self.assertEqual(
            {"base_register": "r31", "offset": 40, "width": "lwz"},
            lead["arguments"][0]["memory_load"],
        )
        self.assertFalse(lead["suppression_eligible"])

    def test_inventories_balanced_dominant_producer_layer(self):
        callers = [
            fixture(0x83010000, ["lwz r3,40(r31)", "bl 0x8240d070"]),
            fixture(0x83020000, ["bl 0x82417060"]),
            fixture(0x83030000, ["bl 0x829f6360"]),
        ]
        document = self.build(
            [*reviewed_fixtures(), *producer_fixtures(), *callers]
        )
        self.assertEqual(3, document["totals"]["indirect_producer_runtime_hooks"])
        self.assertEqual(3, document["totals"]["indirect_producer_calls"])
        self.assertEqual(
            3, document["totals"]["indirect_producer_argument_leads"]
        )
        hooks = {
            item["function_address"]: item
            for item in document["indirect_producer_runtime_hooks"]
        }
        self.assertEqual("829F63FC", hooks["829F6360"]["exit_hook_address"])
        call = next(
            item
            for item in document["indirect_producer_calls"]
            if item["producer_function_address"] == "8240D070"
        )
        self.assertEqual("83010004", call["callsite"])
        lead = next(
            item
            for item in document["indirect_producer_argument_leads"]
            if item["producer_function_address"] == "8240D070"
        )
        self.assertEqual(
            {"base_register": "r31", "offset": 40, "width": "lwz"},
            lead["arguments"][0]["memory_load"],
        )
        self.assertFalse(call["object_identity_proved"])
        self.assertFalse(call["lifetime_proved"])

    def test_proves_live_producer_context_roots(self):
        document = self.build(
            [
                *reviewed_fixtures(),
                *producer_fixtures(),
                *context_fixtures(),
            ]
        )
        self.assertEqual(4, document["totals"]["indirect_context_runtime_hooks"])
        self.assertEqual(5, document["totals"]["indirect_context_roots"])
        hooks = {
            item["function_address"]: item
            for item in document["indirect_context_runtime_hooks"]
        }
        self.assertEqual("82418F38", hooks["82417BC0"]["exit_hook_address"])
        self.assertEqual("829F67B8", hooks["829F6620"]["exit_hook_address"])
        self.assertTrue(hooks["82417BC0"]["invocation_scope_proved"])
        roots = {
            (
                item["context_function_address"],
                item["producer_return_address"],
            ): item
            for item in document["indirect_context_roots"]
        }
        self.assertEqual(
            "r3", roots[("8240CF68", "8240D000")]["derivation"]
        )
        self.assertEqual(
            "r6+59712", roots[("82417BC0", "82418A28")]["derivation"]
        )
        self.assertEqual(
            "r3+59712", roots[("824365B0", "82437048")]["derivation"]
        )
        self.assertEqual(
            "r3", roots[("829F6620", "829F67B0")]["derivation"]
        )
        self.assertFalse(
            roots[("824365B0", "82437048")]["object_lifetime_proved"]
        )
        self.assertFalse(
            roots[("824365B0", "82437048")]["suppression_eligible"]
        )

    def test_rejects_drifted_context_producer_edge(self):
        contexts = context_fixtures()
        contexts[-1] = contexts[-1].replace(
            "bl 0x829f6360", "bl 0x829f5ff0"
        )
        with self.assertRaisesRegex(ValueError, "producer edge drifted"):
            self.build([*reviewed_fixtures(), *producer_fixtures(), *contexts])

    def test_proves_procedural_model_receiver_lifecycle(self):
        document = self.build(
            [
                *reviewed_fixtures(),
                *context_fixtures(),
                *procedural_model_lifecycle_fixtures(),
            ],
            procedural_model_image(),
        )
        lifecycle = document["procedural_model_receiver_lifecycle"]
        self.assertEqual(
            "proceduralGeometry::CProceduralModels", lifecycle["class_name"]
        )
        self.assertEqual(41, lifecycle["vtable_slot"])
        self.assertEqual("82417BC0", lifecycle["dispatch_function_address"])
        self.assertEqual("r3", lifecycle["receiver_entry_register"])
        self.assertEqual("r6+59712", lifecycle["command_root_derivation"])
        self.assertFalse(lifecycle["receiver_is_command_root"])
        self.assertTrue(lifecycle["rtti_vtable_identity_proved"])
        self.assertTrue(lifecycle["constructor_destructor_pair_proved"])
        self.assertEqual(512, lifecycle["object_size"])
        self.assertTrue(lifecycle["visibility_preparation_boundary_proved"])
        self.assertTrue(lifecycle["render_state_boundary_proved"])
        visibility = lifecycle["visibility_selection"]
        self.assertEqual("82E20094", visibility["record_entry_hook_address"])
        self.assertEqual(
            ["82E205E4", "82E206DC"],
            visibility["lod_write_hook_addresses"],
        )
        self.assertEqual("82E206F8", visibility["result_hook_address"])
        self.assertEqual("82E2084C", visibility["record_exit_hook_address"])
        self.assertEqual(18, visibility["selection_byte_offset"])
        self.assertEqual(104, visibility["lod_index_offset"])
        self.assertTrue(visibility["title_visibility_authority"])
        self.assertTrue(visibility["passive_census_required"])
        self.assertFalse(visibility["native_culling_enabled"])
        self.assertFalse(visibility["native_lod_enabled"])
        self.assertTrue(visibility["xenos_authority"])
        self.assertFalse(visibility["suppression_allowed"])
        policy = lifecycle["visibility_policy_inputs"]
        self.assertEqual("82E1FEF0", policy["spatial_prefilter_address"])
        self.assertEqual(4, policy["receiver_spatial_context_pointer_offset"])
        self.assertEqual([16, 32], policy["receiver_spatial_vector_offsets"])
        self.assertEqual(192, policy["category_spatial_stride"])
        self.assertEqual([160, 164, 168], policy["category_spatial_scalar_offsets"])
        self.assertEqual(32, policy["category_query_stride"])
        self.assertEqual("8243F9A0", policy["spatial_helper_address"])
        self.assertEqual("82441048", policy["category_helper_address"])
        self.assertEqual(60, policy["descriptor_distance_scalar_offset"])
        self.assertEqual(44, policy["runtime_distance_scalar_offset"])
        self.assertEqual("82E20134", policy["runtime_threshold_hook_address"])
        self.assertEqual(
            "82E201B0", policy["descriptor_threshold_hook_address"]
        )
        self.assertEqual(
            "82E20258", policy["candidate_threshold_hook_address"]
        )
        self.assertEqual("82E202D8", policy["local_distance_hook_address"])
        self.assertEqual(
            "82E20350", policy["spatial_helper_result_hook_address"]
        )
        self.assertEqual(
            "82E20368", policy["category_helper_result_hook_address"]
        )
        self.assertEqual(
            "ordered_per_record_return_trace", policy["helper_result_capture"]
        )
        self.assertTrue(policy["passive_input_outcome_correlation_required"])
        spatial_helper = policy["spatial_helper_contract"]
        self.assertEqual("8243FD70", spatial_helper["distance_helper_address"])
        self.assertEqual([16, 20, 24], spatial_helper["query_scalar_offsets"])
        self.assertTrue(spatial_helper["distance_test_structure_proved"])
        self.assertFalse(spatial_helper["world_space_semantics_proved"])
        category_helper = policy["category_helper_contract"]
        self.assertEqual(
            [0, 16, 32, 48, 64, 80],
            category_helper["vector_block_offsets"],
        )
        self.assertEqual([0, 1, 2], category_helper["return_domain"])
        self.assertTrue(
            category_helper["six_vector_classifier_structure_proved"]
        )
        self.assertFalse(category_helper["frustum_semantics_proved"])
        self.assertTrue(policy["structural_derivation_proved"])
        self.assertFalse(policy["camera_semantics_proved"])
        self.assertFalse(policy["native_policy_execution_enabled"])
        shadow = lifecycle["visibility_shadow_policy"]
        self.assertEqual("82E20094", shadow["record_entry_hook_address"])
        self.assertEqual(
            "82E20368", shadow["category_helper_result_hook_address"]
        )
        self.assertEqual("82E206F8", shadow["title_result_hook_address"])
        self.assertEqual("82E2084C", shadow["record_exit_hook_address"])
        self.assertEqual(
            "any_nonzero_category_result_selects", shadow["model"]
        )
        self.assertEqual([0, 1, 2], shadow["category_result_domain"])
        self.assertEqual("shadow_only", shadow["native_policy_execution"])
        self.assertFalse(shadow["guest_state_changed"])
        self.assertTrue(shadow["xenos_authority"])
        self.assertFalse(shadow["suppression_allowed"])
        spatial_shadow = lifecycle["visibility_spatial_shadow"]
        self.assertEqual("82E2034C", spatial_shadow["input_hook_address"])
        self.assertEqual("82E20350", spatial_shadow["result_hook_address"])
        self.assertEqual("8243F9A0", spatial_shadow["helper_address"])
        self.assertEqual(
            "8243FD70", spatial_shadow["distance_helper_address"]
        )
        self.assertEqual(52, spatial_shadow["bounded_guest_payload_bytes"])
        self.assertEqual(
            "bounded_spatial_helper_inputs",
            spatial_shadow["guest_payload_read"],
        )
        self.assertFalse(spatial_shadow["guest_state_changed"])
        self.assertTrue(spatial_shadow["xenos_authority"])
        self.assertFalse(spatial_shadow["suppression_allowed"])
        category_shadow = lifecycle["visibility_category_shadow"]
        self.assertEqual("82E20364", category_shadow["input_hook_address"])
        self.assertEqual("82E20368", category_shadow["result_hook_address"])
        self.assertEqual("82441048", category_shadow["helper_address"])
        self.assertEqual(
            [0, 16, 32, 48, 64, 80],
            category_shadow["plane_vector_offsets"],
        )
        self.assertEqual(["v1", "v2"], category_shadow["endpoint_registers"])
        self.assertEqual([1, 1, -1], category_shadow["axis_signs"])
        self.assertEqual(96, category_shadow["bounded_guest_payload_bytes"])
        self.assertEqual(
            "bounded_category_planes", category_shadow["guest_payload_read"]
        )
        self.assertFalse(category_shadow["guest_state_changed"])
        self.assertTrue(category_shadow["xenos_authority"])
        self.assertFalse(category_shadow["suppression_allowed"])
        assembly_shadow = lifecycle["visibility_policy_assembly_shadow"]
        self.assertEqual("82E20094", assembly_shadow["record_entry_hook_address"])
        self.assertEqual("82E2034C", assembly_shadow["spatial_input_hook_address"])
        self.assertEqual("82E20350", assembly_shadow["spatial_result_hook_address"])
        self.assertEqual("82E20364", assembly_shadow["category_input_hook_address"])
        self.assertEqual("82E20368", assembly_shadow["category_result_hook_address"])
        self.assertEqual("82E206F8", assembly_shadow["title_result_hook_address"])
        self.assertEqual("82E2084C", assembly_shadow["record_exit_hook_address"])
        self.assertEqual(
            "independent_spatial_then_category_selection",
            assembly_shadow["model"],
        )
        self.assertEqual(
            "any_nonzero_predicted_category_result_selects",
            assembly_shadow["selection_rule"],
        )
        self.assertEqual(
            148, assembly_shadow["bounded_guest_payload_bytes_per_candidate"]
        )
        self.assertEqual(
            "bounded_spatial_and_category_inputs",
            assembly_shadow["guest_payload_read"],
        )
        self.assertEqual("shadow_only", assembly_shadow["native_policy_execution"])
        self.assertFalse(assembly_shadow["guest_state_changed"])
        self.assertTrue(assembly_shadow["xenos_authority"])
        self.assertFalse(assembly_shadow["suppression_allowed"])
        workset = lifecycle["visibility_policy_workset"]
        self.assertEqual("82E2084C", workset["record_completion_hook_address"])
        self.assertEqual("8241741C", workset["semantic_instance_hook_address"])
        self.assertEqual(4096, workset["capacity"])
        self.assertEqual(
            "independent_policy_to_semantic_candidate_handoff",
            workset["model"],
        )
        self.assertEqual(
            "receiver_generation_record_index", workset["identity"]
        )
        self.assertEqual("bounded_host_visibility_workset", workset["execution"])
        self.assertFalse(workset["title_culling_changed"])
        self.assertFalse(workset["native_draw_enabled"])
        self.assertTrue(workset["xenos_authority"])
        self.assertFalse(workset["suppression_allowed"])
        prepared_candidates = lifecycle["visibility_prepared_candidates"]
        self.assertEqual(
            "8241741C",
            prepared_candidates["semantic_instance_hook_address"],
        )
        self.assertEqual(
            ["82416260", "824162F4"],
            prepared_candidates["semantic_packet_hook_addresses"],
        )
        self.assertEqual(4096, prepared_candidates["capacity"])
        self.assertEqual(
            1, prepared_candidates["maximum_policy_age_frames"]
        )
        self.assertEqual(
            "independent_visibility_selected_and_fresh",
            prepared_candidates["selection"],
        )
        self.assertEqual(
            "exact_semantic_pm4_prepared_draw",
            prepared_candidates["prepared_lineage"],
        )
        self.assertFalse(prepared_candidates["native_draw_enabled"])
        self.assertTrue(prepared_candidates["xenos_draw_preserved"])
        self.assertFalse(prepared_candidates["suppression_allowed"])
        self.assertEqual(
            92, lifecycle["field_layout"]["descriptor_record_stride"]
        )
        self.assertEqual(
            68, lifecycle["field_layout"]["runtime_record_stride"]
        )
        extraction = lifecycle["semantic_instance_extraction"]
        self.assertEqual("8241741C", extraction["hook_address"])
        self.assertEqual("82417B80", lifecycle["render_item_exit_hook_address"])
        self.assertEqual(84, extraction["descriptor_index_caller_stack_offset"])
        self.assertEqual(380, extraction["bounded_payload_bytes_per_observation"])
        self.assertTrue(extraction["argument_mapping_proved"])
        self.assertFalse(extraction["native_rendering_enabled"])
        submission = lifecycle["semantic_submission_extraction"]
        self.assertEqual("82417A74", submission["primary_resource_binding_hook_address"])
        self.assertEqual("82417A9C", submission["secondary_resource_binding_hook_address"])
        self.assertEqual("82417B60", submission["geometry_submission_hook_address"])
        self.assertEqual("82415C50", submission["resource_resolution_result_hook_address"])
        self.assertEqual("82415C6C", submission["resource_bind_dispatch_hook_address"])
        self.assertEqual("82410A58", submission["resource_lookup_function_address"])
        self.assertEqual("82415B64", submission["resource_provider_lookup_hook_address"])
        self.assertEqual("82415B80", submission["resource_provider_primary_predicate_hook_address"])
        self.assertEqual("82415BA4", submission["resource_provider_fallback_predicate_hook_address"])
        self.assertEqual("82415BC0", submission["resource_provider_method_result_hook_address"])
        self.assertEqual("82415BE4", submission["resource_secondary_resolution_result_hook_address"])
        self.assertEqual([24, 36, 40, 44], submission["resource_provider_vtable_method_offsets"])
        self.assertEqual(5, submission["resource_resolution_cache_entry_count"])
        self.assertEqual(12, submission["resource_resolution_cache_entry_stride"])
        self.assertTrue(submission["resource_resolution_cache_shared_across_binding_slots"])
        self.assertTrue(submission["resource_provider_chain_derivation_proved"])
        self.assertFalse(submission["secondary_resolution_semantics_proved"])
        self.assertTrue(submission["resolved_resource_object_derivation_proved"])
        self.assertTrue(submission["descriptor_kind_partition_proved"])
        self.assertTrue(submission["helper_state_partition_proved"])
        self.assertEqual([0, 1], submission["resource_binding_slots"])
        self.assertEqual("834AD4CC", submission["resource_binding_key_cache_address"])
        self.assertEqual(5, submission["resource_binding_key_cache_entry_count"])
        self.assertTrue(submission["resource_binding_key_cache_skips_unchanged_bind"])
        self.assertEqual(13, submission["graphics_submission_primitive"])
        self.assertEqual(4, submission["graphics_submission_count_scale"])
        self.assertTrue(submission["resource_binding_derivation_proved"])
        self.assertTrue(submission["geometry_submission_derivation_proved"])
        self.assertFalse(submission["native_rendering_enabled"])
        draw_association = lifecycle["semantic_draw_association"]
        self.assertEqual(
            "8241741C", draw_association["render_item_entry_hook_address"]
        )
        self.assertEqual(
            "82417B80", draw_association["render_item_exit_hook_address"]
        )
        self.assertEqual(
            ["82410328", "829F7CB0"],
            draw_association["title_draw_packet_hook_addresses"],
        )
        self.assertEqual(
            ["82416260", "824162F4"],
            draw_association["semantic_draw_packet_hook_addresses"],
        )
        self.assertEqual(
            "82415CE0", draw_association["graphics_submission_wrapper_address"]
        )
        self.assertEqual(
            "82415F68", draw_association["graphics_submission_emitter_address"]
        )
        self.assertEqual(
            "PM4_DRAW_INDX", draw_association["semantic_draw_packet_opcode"]
        )
        self.assertTrue(draw_association["semantic_pm4_packet_construction_proved"])
        self.assertTrue(
            draw_association[
                "semantic_prepared_contract_runtime_join_required"
            ]
        )
        self.assertEqual(
            "immutable_template_and_dynamic_resource_instance",
            draw_association["semantic_catalog_classification"],
        )
        self.assertTrue(
            draw_association["semantic_batch_admission_census_required"]
        )
        self.assertEqual(
            "exact_consecutive_prepared_draw_order",
            draw_association["semantic_batch_ordering"],
        )
        self.assertTrue(
            draw_association[
                "semantic_batch_equivalence_ladder_required"
            ]
        )
        self.assertEqual(
            "resource_free_layout_and_prepared_state",
            draw_association["semantic_batch_pipeline_identity"],
        )
        self.assertFalse(
            draw_association["semantic_batch_execution_enabled"]
        )
        self.assertTrue(
            draw_association["semantic_state_cache_required"]
        )
        self.assertEqual(
            "set_associative_lru",
            draw_association["semantic_state_cache_policy"],
        )
        self.assertEqual(
            "compact:64,balanced:256,headroom:1024",
            draw_association["semantic_state_cache_profiles"],
        )
        self.assertFalse(
            draw_association["semantic_state_cache_execution_enabled"]
        )
        self.assertTrue(draw_association["render_item_invocation_scope_proved"])
        self.assertTrue(draw_association["submission_before_draw_dispatch_proved"])
        self.assertEqual(160, draw_association["graphics_submission_vtable_offset"])
        self.assertTrue(draw_association["direct_title_packet_overlap_probe"])
        self.assertTrue(
            draw_association["indirect_packet_constructor_overlap_probe"]
        )
        self.assertFalse(
            draw_association["physical_pm4_packet_correlation_proved"]
        )
        self.assertFalse(draw_association["prepared_draw_lineage_proved"])
        self.assertFalse(draw_association["native_rendering_enabled"])
        self.assertFalse(lifecycle["suppression_eligible"])

    def test_rejects_drifted_procedural_model_vtable_slot(self):
        image = bytearray(procedural_model_image())
        offset = 0x82002C00 - MODULE.IMAGE_BASE
        image[offset : offset + 4] = (0x824365B0).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "RTTI/vtable evidence drifted"):
            self.build(
                [
                    *reviewed_fixtures(),
                    *context_fixtures(),
                    *procedural_model_lifecycle_fixtures(),
                ],
                bytes(image),
            )

    def test_rejects_drifted_resource_provider_route(self):
        lifecycle = [
            chunk.replace("lwz r11,40(r11)", "lwz r11,48(r11)")
            for chunk in procedural_model_lifecycle_fixtures()
        ]
        with self.assertRaisesRegex(ValueError, "provider chain evidence drifted"):
            self.build(
                [*reviewed_fixtures(), *context_fixtures(), *lifecycle],
                procedural_model_image(),
            )

    def test_runtime_hooks_are_default_off_bounded_and_passive(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        capture = (
            ROOT / "tools/capture-native-renderer-dispatch.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon_shift_native_renderer_dispatch_discovery, false", hooks
        )
        self.assertIn("kDispatchCallerCapacity = 256", hooks)
        self.assertIn('"suppression_allowed", "false"', hooks)
        claim = hooks.index("entry.key.compare_exchange_strong")
        initial_count = hooks.index("entry.calls.store(1", claim)
        first_sample = hooks.index("entry.first_frame.store", claim)
        self.assertLess(initial_count, first_sample)
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawIndexedDispatch"'), 1
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawImmediateDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawAdapterDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawPacketSubmission"'),
            2,
        )
        for address in (
            "824095B4",
            "82416EFC",
            "8246FC1C",
            "8263BD64",
            "829E8E88",
            "829EC49C",
        ):
            self.assertIn(f"address = 0x{address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectPacket{address}"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("82409398", "8240939C", "82409660"),
            ("82416A00", "82416A04", "82417054"),
            ("8246FB98", "8246FB9C", "8246FC78"),
            ("8263BCB8", "8263BCBC", "8263BDF0"),
            ("829E8E00", "829E8E04", "829E8ED4"),
            ("829EC400", "829EC404", "829EC5AC"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectConstructor{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectConstructor{function}Exit"'
                ),
                1,
            )
        for name, entry, exit_address in (
            ("Constructor", "82E1C9A4", "82E1CA0C"),
            ("Destructor", "82E1CA2C", "82E1CBD0"),
            ("Visibility", "82E1FD04", "82E208CC"),
            ("RenderState", "824170DC", "82417410"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveProceduralModel{name}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveProceduralModel{name}Exit"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("82409668", "8240966C", "8240983C"),
            ("824167F8", "824167FC", "82416898"),
            ("8246E8F8", "8246E8FC", "8246E938"),
            ("829F5FF0", "829F5FF4", "829F6358"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectOwner{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectOwner{function}Exit"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("8240D070", "8240D074", "8240D1F0"),
            ("82417060", "82417064", "824170C0"),
            ("829F6360", "829F6364", "829F63FC"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectProducer{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectProducer{function}Exit"'
                ),
                1,
            )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryBeginDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryEndDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveResolveControllerDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveResolveSetupDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryOwnerDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count(
                'name = "PinyonShiftObserveBinningScissorStateDispatch"'
            ),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveBinningStateResetDispatch"'),
            1,
        )
        self.assertIn('address = 0x824079BC', analysis)
        self.assertIn('address = 0x8240F4DC', analysis)
        self.assertIn('address = 0x82410328', analysis)
        self.assertIn('address = 0x824587DC', analysis)
        self.assertIn('address = 0x82458A8C', analysis)
        self.assertIn('address = 0x829F21A4', analysis)
        self.assertIn('address = 0x829F2284', analysis)
        self.assertIn('address = 0x829F7C74', analysis)
        self.assertIn('address = 0x829F7CB0', analysis)
        self.assertIn('address = 0x82D951E4', analysis)
        self.assertIn('address = 0x82413ABC', analysis)
        self.assertIn('address = 0x824736F4', analysis)
        self.assertEqual(
            analysis.count(
                'registers = ["r3", "r4", "r5", "r6", "r7", "r8", '
                '"r9", "r10", "r12"]'
            ),
            27,
        )
        self.assertIn(
            "REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY", capture
        )
        self.assertIn("REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS", capture)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SCENE", capture)
        self.assertIn("[string]$Scene = 'unmarked'", capture)
        self.assertIn("launch-preview.ps1", capture)
        for forbidden in ("SetDrawSuppression", "SetCopySuppression"):
            self.assertNotIn(forbidden, hooks + analysis + capture)


if __name__ == "__main__":
    unittest.main()
