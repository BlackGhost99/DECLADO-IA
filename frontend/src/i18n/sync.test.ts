import {describe,expect,it} from "vitest";
import {effectiveLocale} from "./sync";
import type {Me} from "../api";
describe("effectiveLocale",()=>{
 it("prefers account language",()=>{
 const profile: Me = {id:"test",email:"demo@example.test",full_name:"Demo",is_reference_manager:false,interface_locale:"en",active_organization_id:null,memberships:[]};
 expect(effectiveLocale(profile)).toBe("en");
 });
});
