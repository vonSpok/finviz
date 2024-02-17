import finviz as fv

stock = fv.Stock()
info = stock.get_fund('AAPL')
print(info)
