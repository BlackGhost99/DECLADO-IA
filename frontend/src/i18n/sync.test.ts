import {describe,expect,it} from "vitest";
import {effectiveLocale} from "./sync";
import type {Me} from "../api";
describe("effectiveLocale",()=>{
 it("prefers account language",()=>{
 const profile={interface_locale:"en",active_organization_id:null,memberships:[]} as Me;
 expect(effectiveLocale(profile)).toBe("en");
 });
});
