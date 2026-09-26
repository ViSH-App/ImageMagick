#include <MagickWand/MagickWand.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    const char *formats[] = {"JPEG", "PNG", "WEBP", "AVIF", "GIF", "TIFF", "BMP", "ICO"};
    MagickWandGenesis();
    for (size_t i = 0; i < sizeof(formats) / sizeof(formats[0]); i++) {
        MagickWand *wand = NewMagickWand();
        MagickWand *decoded = NewMagickWand();
        size_t length = 0;
        if (!MagickSetSize(wand, 16, 16) || !MagickReadImage(wand, "xc:red") ||
            !MagickSetImageFormat(wand, formats[i])) return 1;
        unsigned char *blob = MagickGetImageBlob(wand, &length);
        if (!blob || !length || !MagickReadImageBlob(decoded, blob, length) ||
            MagickGetImageWidth(decoded) != 16 || MagickGetImageHeight(decoded) != 16) {
            fprintf(stderr, "Round trip failed: %s\n", formats[i]);
            return 1;
        }
        printf("PASS %s (%zu bytes)\n", formats[i], length);
        MagickRelinquishMemory(blob);
        DestroyMagickWand(wand);
        DestroyMagickWand(decoded);
    }
    MagickWandTerminus();
    return 0;
}
