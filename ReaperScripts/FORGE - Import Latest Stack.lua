-- FORGE - Import Latest Stack.lua
-- Inserts the most recent FORGE export package into the current REAPER project.

local appdata = os.getenv("APPDATA")
if not appdata or appdata == "" then
  reaper.MB("Windows APPDATA could not be located.", "FORGE", 0)
  return
end

local marker = appdata .. "\\OJ Labs\\FORGE\\latest_export.txt"
local f = io.open(marker, "r")
if not f then
  reaper.MB("No FORGE export marker was found.\n\nRun Produce Vocal or Build Stack in the FORGE VST3 first.", "FORGE", 0)
  return
end

local folder = f:read("*l") or ""
local startText = f:read("*l") or ""
f:close()
if folder == "" then return end
local startPos = tonumber(startText) or reaper.GetCursorPosition()

local parts = {
  {"01_MASTER_LEAD_DRY.wav",    "FORGE - Lead Dry"},
  {"02_MASTER_LEAD_MIXED.wav",  "FORGE - Lead Mixed"},
  {"03_DOUBLE_L.wav",           "FORGE - Double L"},
  {"04_DOUBLE_R.wav",           "FORGE - Double R"},
  {"05_UPPER_HARMONY.wav",      "FORGE - Upper Harmony"},
  {"06_LOWER_HARMONY.wav",      "FORGE - Lower Harmony"},
  {"07_HIGH_OCTAVE.wav",        "FORGE - High Octave"},
  {"08_LOW_OCTAVE.wav",         "FORGE - Low Octave"},
  {"09_STACK_REFERENCE_MIX.wav", "FORGE - Stack Reference"},
}

local function join(a, b)
  if a:sub(-1) == "\\" or a:sub(-1) == "/" then return a .. b end
  return a .. "\\" .. b
end

local insertIndex = reaper.CountTracks(0)
local selected = reaper.GetSelectedTrack(0, 0)
if selected then insertIndex = math.floor(reaper.GetMediaTrackInfo_Value(selected, "IP_TRACKNUMBER")) end

local imported = 0
reaper.Undo_BeginBlock()
reaper.PreventUIRefresh(1)
for _, part in ipairs(parts) do
  local path = join(folder, part[1])
  local test = io.open(path, "rb")
  if test then
    test:close()
    reaper.InsertTrackAtIndex(insertIndex, true)
    local track = reaper.GetTrack(0, insertIndex)
    if track then
      reaper.GetSetMediaTrackInfo_String(track, "P_NAME", part[2], true)
      local item = reaper.AddMediaItemToTrack(track)
      local take = reaper.AddTakeToMediaItem(item)
      local source = reaper.PCM_Source_CreateFromFile(path)
      if item and take and source then
        reaper.SetMediaItemTake_Source(take, source)
        reaper.GetSetMediaItemTakeInfo_String(take, "P_NAME", part[2], true)
        local length = reaper.GetMediaSourceLength(source)
        reaper.SetMediaItemInfo_Value(item, "D_POSITION", startPos)
        reaper.SetMediaItemInfo_Value(item, "D_LENGTH", length)
        imported = imported + 1
      end
    end
    insertIndex = insertIndex + 1
  end
end
reaper.PreventUIRefresh(-1)
reaper.TrackList_AdjustWindows(false)
reaper.UpdateArrange()
reaper.Undo_EndBlock("FORGE: Import latest vocal stack", -1)
reaper.MB("Imported " .. tostring(imported) .. " FORGE stems.", "FORGE", 0)
