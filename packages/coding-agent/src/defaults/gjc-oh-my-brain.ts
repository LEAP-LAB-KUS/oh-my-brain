import type { ExtensionFactory } from "../extensibility/extensions/types";
import ohMyBrainExtensionFactory from "./gjc/extensions/oh-my-brain/index";

export const BUNDLED_OH_MY_BRAIN_EXTENSION_ID = "bundled:oh-my-brain";

export function getBundledOhMyBrainExtensionFactory(): ExtensionFactory {
	return ohMyBrainExtensionFactory;
}
