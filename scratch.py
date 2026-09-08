from textwrap import dedent

def check_nusiz(val):
    sizes = {
        0: "1 copy",
        1: "2 copies close (16px gap)",
        2: "2 copies med (32px gap)",
        3: "3 copies close (16px gap)",
        4: "2 copies far (64px gap)",
        5: "double size",
        6: "3 copies med (32px gap)",
        7: "quad size"
    }
    return sizes.get(val, "unknown")

print("NUSIZ 6 is:", check_nusiz(6))
