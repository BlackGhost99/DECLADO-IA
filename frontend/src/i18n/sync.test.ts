import {describe,expect,it} from "vitest";
import {effectiveLocale} from "./sync";
import type {Me} from "../api";
describe("effectiveLocale",()=>{
 it("prefers account language",()=>{
 const profile: Me = {id:"test",email:"demo@example.test",full_name:"Demo",is_reference_manager:false,is_platform_operator:false,interface_locale:"en",active_organization_id:null,memberships:[],mfa_enabled:false,mfa_verified_session:false,mfa_required_for_access:false};
 expect(effectiveLocale(profile)).toBe("en");
 });
});
