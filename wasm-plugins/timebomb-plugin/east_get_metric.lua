local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random(); math.random(); math.random()

local url = "http://node2.gangmuk-184284.istio-pg0.clemson.cloudlab.us:32340"

local function get()
  local method = "GET"
  local path = url .. "/start"
  local headers = {}
  headers["x-slate-destination"] = "east"
  -- headers["Content-Type"] = "application/x-www-form-urlencoded"
  return wrk.format(method, path, headers, nil)
end


request = function()
  return get(url)
end
