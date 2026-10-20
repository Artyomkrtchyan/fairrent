// Synthetic demo photos. These are AI-generated architectural images, NOT
// photos of real advertised properties. Every photo area also shows a visible
// "Demo image" label in the UI.
import demoCascade from "@/assets/demo-cascade.jpg";
import demoLoft from "@/assets/demo-loft.jpg";
import demoPanel from "@/assets/demo-panel.jpg";
import demoPremium from "@/assets/demo-premium.jpg";

/** Resolves a listing's `thumbnailUrl` key to the bundled demo image.
 *  An unknown key resolves to `undefined`, which the photo component treats
 *  exactly like "no photo" and shows the architectural placeholder. */
export const LISTING_PHOTOS: Record<string, string> = {
  "demo-cascade": demoCascade,
  "demo-premium": demoPremium,
  "demo-panel": demoPanel,
  "demo-loft": demoLoft,
};
