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
        // A blob has no filename extension. Supply the known decoder format, as
        // consumers do through their filename or format prefix (notably for ICO).
        if (!MagickSetFormat(decoded, formats[i])) return 1;
        unsigned char *blob = MagickGetImageBlob(wand, &length);
        if (!blob || !length || !MagickReadImageBlob(decoded, blob, length) ||
            MagickGetImageWidth(decoded) != 16 || MagickGetImageHeight(decoded) != 16) {
            ExceptionType severity;
            char *error = MagickGetException(decoded, &severity);
            fprintf(stderr, "Round trip failed: %s: %s (%zu bytes)\n", formats[i], error, length);
            MagickRelinquishMemory(error);
            return 1;
        }
        PixelWand *pixel = NewPixelWand();
        if (!MagickGetImagePixelColor(decoded, 8, 8, pixel) ||
            PixelGetRed(pixel) < 0.9 || PixelGetGreen(pixel) > 0.1 || PixelGetBlue(pixel) > 0.1) {
            fprintf(stderr, "Decoded pixel mismatch: %s\n", formats[i]);
            return 1;
        }
        DestroyPixelWand(pixel);
        printf("PASS %s (%zu bytes)\n", formats[i], length);
        MagickRelinquishMemory(blob);
        DestroyMagickWand(wand);
        DestroyMagickWand(decoded);
    }
    MagickWandTerminus();
    return 0;
}
