import {describe,expect,it} from "vitest";
import {direction,isLocale} from "./index";
describe("language foundation",()=>{
 it("supports four locales",()=>{expect(["fr","en","es","ar"].every(isLocale)).toBe(true);expect(isLocale("pt")).toBe(false);});
 it("sets Arabic right-to-left only",()=>{expect(direction("ar")).toBe("rtl");expect(direction("fr")).toBe("ltr");});
});
