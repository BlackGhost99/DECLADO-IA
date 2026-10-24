import {useCallback,useEffect,useRef} from "react";
import type {Me} from "../api";
import {request} from "../api";
import {isLocale,type Locale,useI18n} from "./index";
export function effectiveLocale(profile:Me):Locale {
 if(isLocale(profile.interface_locale))return profile.interface_locale;
 const org=profile.memberships.find(m=>m.organization.id===profile.active_organization_id);
 return org&&isLocale(org.organization.default_locale)?org.organization.default_locale:"fr";
}
export function useLocaleSync(){
 const {locale,setLocale}=useI18n();
 const profileRef=useRef<Me|null>(null);
 const confirmed=useRef<Locale|null>(null);
 const generation=useRef(0);
 const sequence=useRef(0);
 const onAuthenticated=useCallback((profile:Me)=>{
   generation.current++;sequence.current++;profileRef.current=profile;
   const value=effectiveLocale(profile);confirmed.current=value;setLocale(value);
 },[setLocale]);
 const onSignedOut=useCallback(()=>{
   generation.current++;sequence.current++;profileRef.current=null;confirmed.current=null;
 },[]);
 useEffect(()=>{
  if(!profileRef.current||confirmed.current===locale)return;
  const g=generation.current;const s=++sequence.current;
  const old=confirmed.current;confirmed.current=locale;
  void request<{locale:Locale}>("PUT","/me/locale",{locale}).then(response=>{
   if(g!==generation.current||s!==sequence.current)return;
   confirmed.current=response.locale;
   if(response.locale!==locale)setLocale(response.locale);
  }).catch(()=>{
   if(g!==generation.current||s!==sequence.current)return;
   if(old){confirmed.current=old;setLocale(old);}
  });
 },[locale,setLocale]);
 return {onAuthenticated,onSignedOut};
}
