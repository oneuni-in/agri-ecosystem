/**
 * Inline SVG outlines for Tamil/Devanagari glyph clusters, used in place of
 * the literal characters wherever they'd otherwise render on every English
 * page. Fonts download on Unicode-range glyph *usage*, not on the text
 * actually being read - so `த`/`हिं`/`दूध` as literal characters anywhere in
 * the always-on header (locale switcher label, site tagline) forced ~121 KB
 * of Noto Sans Devanagari onto every non-hi page for text nobody reads as
 * running content (issue #45). Tamil script stays as real text elsewhere -
 * en/ta pages need it anyway for genuine vernacular content - only these
 * two always-rendered, non-content spots were worth SVG-ifying.
 *
 * Paths were extracted from the actual build output fonts (`Noto Sans
 * Tamil` / `Noto Sans Devanagari`, the same weight each call site renders
 * at) via fontTools + HarfBuzz shaping - so the Devanagari matra/anusvara
 * reordering in "हिं" and the द+ू ligature + ध sequence in "दूध" are
 * positioned exactly as the real font would place them - then flipped into
 * SVG's y-down coordinate space. `fill="currentColor"` follows the
 * surrounding text color; each glyph is sized in `em` so it scales with
 * whatever font-size its call site uses.
 */
export function TamilGlyph() {
  return (
    <svg
      viewBox="0 0 833 883"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      style={{ height: "1em", width: "0.94em" }}
    >
      <path d="M253 574Q178 574 121.0 553.5Q64 533 32.0 493.5Q0 454 0 397Q0 342 32.5 301.5Q65 261 136.5 238.0Q208 215 323 215H490Q590 215 667.0 239.0Q744 263 788.5 317.5Q833 372 833 465Q833 533 804.5 580.5Q776 628 723 663Q690 685 643.5 700.5Q597 716 534.5 723.5Q472 731 390 731H312Q251 731 225.5 736.5Q200 742 184 753Q168 765 159.0 783.5Q150 802 150 834Q150 845 151.0 855.0Q152 865 153 876L7 883Q4 862 2.5 841.5Q1 821 1 797Q1 752 19.0 718.5Q37 685 67 664Q87 650 112.0 641.0Q137 632 174.0 628.0Q211 624 266 624H356Q443 624 499.0 617.5Q555 611 589.5 597.0Q624 583 646 560Q666 540 676.0 513.5Q686 487 686 453Q686 409 667.5 382.0Q649 355 618.5 340.5Q588 326 551.5 321.0Q515 316 479 316H304Q269 316 237.5 319.5Q206 323 184 334Q165 344 156.0 359.0Q147 374 147 394Q147 431 178.5 449.0Q210 467 263 467Q302 467 329.5 455.0Q357 443 372.0 411.5Q387 380 387 324V107H236V260L102 276V0H721V107H532V322Q532 392 518.5 432.5Q505 473 480 501Q444 541 386.0 557.5Q328 574 253 574Z" />
    </svg>
  );
}

/** The switcher label's "हिं" cluster (ह + ि + ं). Used inside a `<Link>`
 * that already carries `aria-label="हिं"`, so this stays purely decorative. */
export function DevanagariGlyph() {
  return (
    <svg
      viewBox="0 0 875 1059"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      style={{ height: "1em", width: "0.83em" }}
    >
      <path d="M78 281Q64 258 55.0 231.0Q46 204 46 172Q46 91 108.0 45.5Q170 0 278 0Q389 0 482.5 37.0Q576 74 649.0 137.0Q722 200 772 281H635Q598 233 548.0 194.5Q498 156 437.5 134.0Q377 112 311 112Q249 112 217.5 136.5Q186 161 186 204Q186 226 193.5 244.5Q201 263 212 281ZM217 386V896H77V386H0V274H309V386ZM686 86Q686 53 708.5 30.5Q731 8 764 8Q797 8 819.0 30.5Q841 53 841 86Q841 120 819.0 142.5Q797 165 764 165Q731 165 708.5 142.5Q686 120 686 86Z M435 701Q390 670 369.0 637.5Q348 605 348 569Q348 508 393.0 476.0Q438 444 522 444H645V386H294V274H875V386H783V551H543Q513 551 499.0 561.0Q485 571 485 590Q485 606 497.0 620.0Q509 634 532 647ZM640 845Q662 831 674.0 814.5Q686 798 686 780Q686 757 665.5 741.5Q645 726 599 726Q545 726 516.5 746.5Q488 767 488 803Q488 833 511.0 857.0Q534 881 583.0 903.0Q632 925 707 950L649 1059Q547 1029 480.5 992.0Q414 955 381.5 908.5Q349 862 349 805Q349 739 383.5 698.0Q418 657 476.0 637.5Q534 618 606 618Q683 618 731.0 640.0Q779 662 801.5 697.5Q824 733 824 775Q824 814 807.5 847.0Q791 880 754 911Z" />
    </svg>
  );
}

/**
 * The site tagline's "दूध" ("milk"): द+ू (the font ligates these into one
 * glyph) followed by ध. Unlike the switcher, this isn't inside an element
 * that already carries an equivalent `aria-label`, so it supplies its own
 * accessible name via `role="img"` on the wrapper - a visually-hidden text
 * *node* would work for sighted-hidden screen-reader text, but would still
 * lay out and repaint the literal characters, re-triggering the exact font
 * download this component exists to avoid.
 */
export function DudhGlyph() {
  return (
    <span role="img" aria-label="दूध">
      {/* Tailwind's preflight sets `svg { display: block }`, which would
          otherwise force this onto its own line inside the tagline's
          running text - override back to inline so it flows like a word. */}
      <svg
        viewBox="0 0 1160 926"
        aria-hidden="true"
        focusable="false"
        fill="currentColor"
        style={{ display: "inline", height: "1em", width: "1.25em", verticalAlign: "-0.08em" }}
      >
        <path d="M405 692Q386 651 372.0 609.5Q358 568 350 535L337 499Q330 482 327.0 467.0Q324 452 324 437Q324 408 342.0 391.0Q360 374 392 374Q429 374 453.0 398.0Q477 422 477 453Q477 480 460.5 501.0Q444 522 412 536L395 540Q371 548 349.0 552.5Q327 557 293 557Q249 557 206.0 546.0Q163 535 128.5 511.0Q94 487 73.5 449.0Q53 411 53 357Q53 266 115.5 221.5Q178 177 299 177H370L354 212V81H0V10H541V81H435V247H311Q223 247 178.5 274.5Q134 302 134 361Q134 420 177.0 452.0Q220 484 292 484Q309 484 329.5 481.0Q350 478 372 468L417 520Q429 554 444.0 588.5Q459 623 481 662ZM622 926Q585 846 551.0 798.5Q517 751 480.0 730.0Q443 709 396 709Q351 709 326.0 728.0Q301 747 301 782Q301 805 311.5 819.5Q322 834 340.0 841.0Q358 848 379 848Q401 848 420.5 842.5Q440 837 460 824L490 888Q467 905 440.0 912.5Q413 920 381 920Q308 920 267.0 881.5Q226 843 226 780Q226 714 272.0 677.5Q318 641 397 641Q465 641 516.5 669.5Q568 698 610.0 753.5Q652 809 690 890Z M1160 81H1057V632H976V447L994 472Q970 497 928.0 513.5Q886 530 827 530Q767 530 722.5 511.0Q678 492 653.5 458.0Q629 424 629 379Q629 347 644.5 316.5Q660 286 697 267Q699 265 702.5 263.5Q706 262 710 260Q732 247 758.0 243.0Q784 239 812 239Q826 239 840.5 240.5Q855 242 866 244L858 314Q848 312 838.0 311.5Q828 311 814 311Q780 311 756.5 319.0Q733 327 721.0 343.0Q709 359 709 383Q709 421 742.0 440.5Q775 460 826 460Q879 460 922.0 435.5Q965 411 990 372L976 424V81H914V10H1160ZM703 301Q669 285 641.0 261.5Q613 238 597.0 206.5Q581 175 581 136Q581 72 621.0 36.0Q661 0 730 0Q775 0 804.0 15.0Q833 30 846.5 55.0Q860 80 860 111Q860 137 849.5 160.0Q839 183 816 204L756 168Q770 154 776.5 140.0Q783 126 783 112Q783 89 769.5 76.5Q756 64 730 64Q698 64 678.5 85.0Q659 106 659 142Q659 180 682.0 207.0Q705 234 748 254Z" />
      </svg>
    </span>
  );
}
