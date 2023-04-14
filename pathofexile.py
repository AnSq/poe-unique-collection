#!/usr/bin/env python

import time
import requests
import json
from collections import deque
import logging

from typing import Any


ROOT = "https://api.pathofexile.com"
TIME_PADDING = 1

STASH_TAB_COLOUR_NAMES = {
    "7c5436" : "brown1",
    "bf5e00" : "brown2",
    "ffbf80" : "brown3",
    "590000" : "red1",
    "bf0000" : "red2",
    "ff8080" : "red3",
    "730055" : "magenta1",
    "cc009a" : "magenta2",
    "ff80df" : "magenta3",
    "2c0059" : "purple1",
    "5a00b3" : "purple2",
    "c080ff" : "purple3",
    "80"     : "blue1",
    "ff"     : "blue2",
    "80b3ff" : "blue3",
    "4d00"   : "green1",
    "bf00"   : "green2",
    "80ff80" : "green3",
    "638000" : "lime1",
    "bff500" : "lime2",
    "f0ff80" : "lime3",
    "ffaa00" : "yellow1",
    "ffd500" : "yellow2",
    "ffff99" : "yellow3",
    "323232" : "black",
    "888888" : "grey",
    "dddddd" : "white",
}

log = logging.getLogger(__name__)



class PoEError (Exception):
    """represents an error returned by the API"""
    def __init__(self, message:str="", status_code:int=None, error_code:int=None) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message, status_code, error_code)



class RateLimitOnCooldownError (Exception):
    """raised by a non-blocking request that would exceed the rate limit"""
    def __init__(self, retry_after:int) -> None:
        self.retry_after = retry_after
        super().__init__({"retry_after" : retry_after})



class RateLimiter:
    def __init__(self) -> None:
        self.policies:dict[str,dict[int,RateLimitRule]]  = {}  # {policy : {period : RateLimitRule}}
        self.endpoint_policies:dict[tuple[str,bool],str] = {}  # {(endpoint, has_args) : policy}


    def update(self, endpoint, has_args, headers):
        """update the RateLimiter after a request"""
        ep = (endpoint, has_args)
        policy = self.parse_headers(headers)
        if ep not in self.endpoint_policies:
            self.endpoint_policies[ep] = policy
        else:
            assert self.endpoint_policies[ep] == policy


    def parse_headers(self, headers:dict[str,str]) -> str:
        """update the RateLimiter from the given response headers and return the policy that applied to the request"""
        # adapted from https://github.com/BPL-Development-Team/poe-client/blob/3b31b0dbed753dac9ef79844eb103b57b5cf865e/poe_client/rate_limiter.py#L103

        if not headers.get("X-Rate-Limit-Policy"):
            # endpoint has no rate limiting
            return ""
        
        rule_names = headers["X-Rate-Limit-Rules"].split(",")
        if len(rule_names) > 1:
            raise NotImplementedError(f"processing for multiple X-Rate-Limit-Rules is not implemented (found {rule_names})")

        for rule_name in rule_names:
            policy = f"{rule_name}/{headers['X-Rate-Limit-Policy']}"
            
            if policy not in self.policies:
                self.policies[policy] = {}
            
            rule_specs = headers[f"X-Rate-Limit-{rule_name}"].split(",")
            for rule_spec in rule_specs:
                max_hits, period, penalty = (int(x) for x in rule_spec.split(":"))

                if period not in self.policies[policy]:
                    self.policies[policy][period] = RateLimitRule(policy, max_hits, period, penalty)
            
            states = headers[f"X-Rate-Limit-{rule_name}-State"].split(",")
            for state in states:
                current_hits, period, time_restricted = (int(x) for x in state.split(":"))
                self.policies[policy][period].state.update(current_hits, time_restricted)
            
        return policy  # only works for one rule
    

    def time_until_ready(self, endpoint:str, has_args:bool) -> int:
        """get the number of seconds until the indicated request is allowed"""
        ep = (endpoint, has_args)

        if ep not in self.endpoint_policies:
            # never used this endpoint before
            return 0
        
        policy = self.endpoint_policies[ep]
        result = 0
        for rule in self.policies[policy].values():
            t = rule.time_until_ready()
            if t:
                log.debug(f"time_until_ready {rule.name()} {t:.2f}")
            result = max(result, t)
        return result



class RateLimitRule:
    """a single rate limit rule, with a maximum number of hits over a given period, and a time penalty for going over"""
    def __init__(self, policy:str, max_hits:int, period:int, penalty:int) -> None:
        self.policy   = policy
        self.max_hits = max_hits
        self.period   = period
        self.penalty  = penalty
        self.state    = RateLimitState(0, period, 0)
    

    def name(self):
        """get the name of this rule"""
        return f"{self.policy}/{self.max_hits}:{self.period}:{self.penalty}"
    

    def time_until_ready(self):
        """get the number of seconds until a new request will not violate this rule"""
        now = time.time()
        
        # currently restricted
        if self.state.restricted_until > now:
            result = self.state.restricted_until - now + TIME_PADDING
            log.debug(f"rule {self.name()} is currently restricted for {result:.2f} seconds")
            return result

        # immediate request allowed
        self.state.purge_times()
        if len(self.state.times) + 1 <= self.max_hits:
            return 0
        
        # a new request will violate rule
        falloff_index = len(self.state.times) - self.max_hits  # index of the last state.times element that needs to expire for the request to be valid
        if falloff_index > 0:  # this should never be possible
            log.debug(f"falloff_index > 0 ({falloff_index})")
        falloff_time = self.state.times[falloff_index]
        return falloff_time + self.period - time.time() + TIME_PADDING
    
    

class RateLimitState:
    """the current state of a rate limit rule"""
    def __init__(self, current_hits:int, period:int, time_restricted:int) -> None:
        self.current_hits       = current_hits
        self.period             = period
        self.restricted_until   = time.time() + time_restricted
        self.times:deque[float] = deque()
    

    def update(self, current_hits:int, time_restricted:int) -> None:
        """update the rate limit state"""
        self.current_hits    = current_hits
        self.restricted_until = time.time() + time_restricted

        self.times.append(time.time())
        self.purge_times()
    

    def purge_times(self) -> None:
        """remove times older than the period"""
        now = time.time()
        while self.times and (self.times[0] + self.period) <= now:
            self.times.popleft()



class PoEClient:
    """a Path of Exile API client"""
    _ses:requests.Session
    _user_agent:str
    _user_agent_base:str
    _user_agent_suffix:str
    _oauth_config:dict[str,str]
    _secrets:dict[str,str]
    _token:dict[str,Any]
    _ratelimiter:RateLimiter

    def __init__(self, oauth_fname, secrets_fname, token_fname) -> None:
        self._ses = requests.Session()
        self._ratelimiter = RateLimiter()
        self._user_agent_suffix = ""

        with open(oauth_fname) as f:
            self._oauth_config = json.load(f)
        with open(secrets_fname) as f:
            self._secrets = json.load(f)
        self._user_agent_base = f"OAuth {self._oauth_config['client_id']}/{self._oauth_config['version']} (contact: {self._secrets['contact_email']})"
        self._update_user_agent()

        with open(token_fname) as f:
            self._token = json.load(f)
        self._ses.headers.update({"Authorization" : f"Bearer {self._token['access_token']}"})


    def _update_user_agent(self) -> None:
        """update the user-agent header from the current base and suffix"""
        self._user_agent = self._user_agent_base
        if self._user_agent_suffix:
            self._user_agent += " " + self._user_agent_suffix
        self._ses.headers.update({"User-Agent" : self._user_agent})


    def set_user_agent_suffix(self, suffix:str="") -> None:
        """sets the last part of the user-agent (the first part is mandatory as part of the API protocol and cannot be changed)"""
        self._user_agent_suffix = suffix
        self._update_user_agent()


    def _get(self, endpoint:str, response_key:str="", *args:str, has_args=None, blocking=True) -> Any:
        """make a get request"""
        if has_args is None:
            has_args = bool(args)

        url = f"{ROOT}/{endpoint}"
        if args:
            url += "/" + "/".join(args)

        for _ in range(2):  # might violate rate limit base on past session that we don't know about, so try again at most one time
            rate_limit_wait = self._ratelimiter.time_until_ready(endpoint, has_args)
            if rate_limit_wait and not blocking:
                raise RateLimitOnCooldownError(rate_limit_wait)
            if rate_limit_wait > 0:
                log.info(f"rate limited. sleeping for {rate_limit_wait:.2f} seconds")
            time.sleep(rate_limit_wait)

            r = self._ses.get(url)
            self._ratelimiter.update(endpoint, has_args, r.headers)
            if r.status_code != 429:
                break
            log.info(f"rate limit violated. time until ready: {self._ratelimiter.time_until_ready(endpoint, has_args):.2f}")

        data = r.json()
        if r.status_code == 200 and "error" not in data:
            if response_key:
                return data[response_key]
            else:
                return data
        else:
            if "error" in data:
                if not isinstance(data["error"], dict):
                    raise RuntimeError(data)
                else:
                    raise PoEError(data["error"]["message"], r.status_code, data["error"]["code"])
            else:
                raise PoEError("unknown error", r.status_code, None)


    def get_profile(self, blocking=True) -> dict:
        """get the logged-in user's profile"""
        return self._get("profile", blocking=blocking)


    def list_characters(self, blocking=True) -> list[dict[str,Any]]:
        """list all characters"""
        return self._get("character", "characters", blocking=blocking)


    def get_character(self, name:str, blocking=True) -> dict:
        """get a single character"""
        return self._get("character", "character", name, blocking=blocking)


    def list_stashes(self, league:str, flatten=True, blocking=True) -> list[dict[str,Any]]:
        """list stash tabs in the given league"""
        data = self._get("stash", "stashes", league, has_args=False, blocking=blocking)
        if flatten:
            flattened = []
            for stashtab in data:
                if "children" in stashtab:
                    for subtab in stashtab["children"]:
                        flattened.append(subtab)
                else:
                    flattened.append(stashtab)
            return flattened
        else:
            return data


    def get_stash(self, league:str, stash_id:str, substash_id:str|None=None, get_children=False, blocking=True) -> dict[str,Any]:
        """get a stash tab"""
        if substash_id is not None and get_children:
            raise TypeError("get_children is not supported when specifying a substash_id")

        result = None
        if substash_id:
            result = self._get("stash", "stash", league, stash_id, substash_id, blocking=blocking)
        else:
            result = self._get("stash", "stash", league, stash_id, blocking=blocking)
        
        if get_children and ("children" in result):
            for i,sub in enumerate(result["children"]):
                result["children"][i] = self.get_stash(league, stash_id, sub["id"], blocking=blocking)

        return result
