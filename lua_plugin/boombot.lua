script_properties("work-in-pause")
script_author("Chr0niX")

local sampev = require 'lib.samp.events'
local socket = require("socket")

local SERV_HOST = "ugubok.ru"
local SERV_PORT = 51235

local song_requests = {}
local blacklist_nicks = {}

local BLACKLIST_PATH = getGameDirectory() .. "\\moonloader\\boombot_blacklist.json"


---@diagnostic disable-next-line: duplicate-set-field
function string.startswith(String, Start)
   return string.sub(String,1,string.len(Start))==Start
end

local function saveBlacklistToFile()
    local blacklistFile = assert(io.open(BLACKLIST_PATH, "w"))
    blacklistFile:write(encodeJson(blacklist_nicks))
    blacklistFile:close()
end


local function loadBlacklistFromFile()
    local blacklistFile = io.open(BLACKLIST_PATH, "r")
    if blacklistFile == nil then return end
    local blacklistJson = blacklistFile:read()
    blacklistFile:close()
    blacklist_nicks = decodeJson(blacklistJson)
end


function sampev.onServerMessage(color, text)
    local r = text:find("%(.....%) (%S+) %[%d+%]: (.+)")
    if r == nil then return end
    local _, _, nick, msg = text:find("%(.....%) (%S+) %[%d+%]: (.+)")

    local cmd = string.sub(msg, 1, 5)

    if cmd ~= '!play' and cmd ~= '!skip' then return end
    if cmd == '!play' then
        msg = string.sub(msg, 6, -1)
    end

    if blacklist_nicks[nick] ~= nil then 
        print(string.format("Command from %s ignored (blacklist)", nick))
    end

    table.insert(song_requests, {nick, msg})
end


local function sampGetNicknameByIdSafe(id)
    if type(id) == "string" then
        id = tonumber(string.sub(id, 2, #id))
        if id == nil then
            return nil, "Error: id must be a number"
        end
    end

    if id > sampGetMaxPlayerId(false) then
        return nil, string.format("Error: Given id (%d) exceeds the maximum (%d)", id, sampGetMaxPlayerId(false))
    end

    local nickname = sampGetPlayerNickname(id)
    if nickname == nil then
        return nil, string.format("Error: There is no player with id %d", id)
    end

    return nickname, nil
end


function CMD_boomignore(arg)
    if #arg == 0 then
        print("Usage: boomignore [-]<@id | nickname>")
        print("Examples: boomignore @10 - add player [10] to blacklist")
        print("          boomignore Danke - add player Danke to blacklist")
        print("          boomignore -@10 - remove player [10] from blacklist")
        print("          boomignore -Danke - remove player Danke from blacklist")
        return
    end

    local nickname = arg
    local err = nil
    local removeFromBlacklist = false

    if string.startswith(arg, "-") then
        arg = string.sub(arg, 2)
        nickname = arg
        removeFromBlacklist = true
    end

    if string.startswith(arg, "@") then
        nickname, err = sampGetNicknameByIdSafe(string.sub(arg, 2, #arg))
        if err ~= nil then
            print(err)
            return
        end
    end

    if removeFromBlacklist then
        if blacklist_nicks[nickname] == nil then
            print(string.format("%s is not in blacklist!", nickname))
            return
        end
        blacklist_nicks[nickname] = nil
        print(string.format("%s removed from boombot blacklist", nickname))
    else
        blacklist_nicks[nickname] = true
        print(string.format("%s added to boombot blacklist", nickname))
    end

    saveBlacklistToFile()
end


function main()
    sampfuncsRegisterConsoleCommand("boomignore", CMD_boomignore)
    setSampfuncsConsoleCommandDescription("boomignore", "Ignore user from accessing !play / !skip commands")

    loadBlacklistFromFile()

    while true do
        wait(100)
        if #song_requests == 0 then goto end_main_cycle end

        local nick = song_requests[1][1]
        local msg = song_requests[1][2]
        table.remove(song_requests, 1)

        local conn = socket.connect(SERV_HOST, SERV_PORT)
        conn:settimeout(0) -- non-blocking mode
        local data = string.format("%c%s%c%s", #nick, nick, #msg, msg)
        conn:send(data)

        local result, e = conn:receive('*a')
        while e == "timeout" do
            wait(300)
            result, e = conn:receive('*a')
        end

        if result ~= nil and result ~= 'OK' then
            sampSendChat(string.format('!%s', result))
        end

        ::end_main_cycle::
    end
end