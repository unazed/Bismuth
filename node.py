import hashlib
import socket
import sys
import re
import ast
import sqlite3
import time
import requests
import os
import sys

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto import Random

import threading
import SocketServer

#db maintenance
conn=sqlite3.connect("ledger.db")
conn.execute("VACUUM")
conn.close()
conn=sqlite3.connect("mempool.db")
conn.execute("VACUUM")
conn.close()
print "Database maintenance finished"

#connectivity to self node
prod = 0
port = 2829
if prod == 1:
    r = requests.get(r'http://jsonip.com')
    ip= r.json()['ip']
    print 'Your IP is', ip
    sock_self = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #sock_self.settimeout(1)
    result = sock_self.connect_ex((ip,port))
    sock_self.close()
    #result = 0 #enable for test
    if result == 0:
        print "Port is open"   
#get local peers into tuples
    peer_file = open("peers.txt", 'r')
    peer_tuples = []
    for line in peer_file:
        extension = re.findall ("'([\d\.]+)', '([\d]+)'",line)
        peer_tuples.extend(extension)
    peer_file.close()
    peer_me = ("('"+str(ip)+"', '"+str(port)+"')")
    if peer_me not in str(peer_tuples) and result == 0: #stringing tuple is a nasty way
        peer_list_file = open("peers.txt", 'a')
        peer_list_file.write((peer_me)+"\n")
        print "Local node saved to peer file"
        peer_list_file.close()
    else:
        print "Self node already saved"
        
#get local peers into tuples    
else:
   print "Port is not open"
#connectivity to self node
  
#verify blockchain
con = None
conn = sqlite3.connect('ledger.db')
c = conn.cursor()
#c.execute("CREATE TABLE IF NOT EXISTS transactions (block_height, address, to_address, amount, signature, public_key)")
c.execute("SELECT Count(*) FROM transactions")
db_rows = c.fetchone()[0]
print "Total steps: "+str(db_rows)

#verify genesis
c.execute("SELECT to_address FROM transactions ORDER BY block_height ASC LIMIT 1")
genesis = c.fetchone()[0]
print "Genesis: "+genesis
if str(genesis) != "352e5c8ca3751061e63ecb45d4c8dda4deaf773b6cb1e6c18be80072": #change this line to your genesis address if you want to clone
    print "Invalid genesis address"
    sys.exit(1)
#verify genesis

try:
    for row in c.execute('SELECT * FROM transactions ORDER BY block_height'):
        db_block_height = row[0]
        db_timestamp = row[1]
        db_address = row[2]
        db_to_address = row[3]
        db_amount = row [4]
        db_signature = row[5]
        db_public_key = RSA.importKey(row[6])
        db_txhash = row[7]
        db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount) 

        #print db_transaction

        db_signature_tuple = ast.literal_eval(db_signature) #converting to tuple

        invalid = 0
        
        if db_public_key.verify(db_transaction, db_signature_tuple) == True: #TODO: ADD TXHASH VALIDATION?
            pass
        else:
            #print "Step "+str(db_block_height)+" is invalid"
            invalid = invalid + 1
            if db_block_height == str(1):
                print "Your genesis signature is invalid, someone meddled with the database"
                sys.exit(1)

    if invalid > 0:
        print str(invalid)+" of the transactions in the local ledger are invalid"

    if invalid == 0:
        print "All transacitons in the local ledger are valid"            
        
except sqlite3.Error, e:                        
    print "Error %s:" % e.args[0]
    sys.exit(1)                        
finally:                        
    if conn:
        conn.close()
#verify blockchain

### LOCAL CHECKS FINISHED ###

class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self): #server defined here
        while True:
            try:
                data = self.request.recv(11)
                cur_thread = threading.current_thread()
                
                #print "received: "+data

                if data == 'helloserver':
                    with open ("peers.txt", "r") as peer_list:
                        peers=peer_list.read()
                        print peers
                        self.request.sendall("peers______")
                        time.sleep(0.1)
                        self.request.sendall(peers)
                        time.sleep(0.1)
                        
                    print "Sending sync request"
                    self.request.sendall("sync_______")
                    time.sleep(0.1)

                if data == "blockfound_":                  
                    print "Node has the block" #node should start sending txs in this step
                    #todo critical: make sure that received block height is correct
                    data = self.request.recv(2048)
                    #verify
                    sync_list = ast.literal_eval(data) #this is great, need to add it to client -> node sync
                    received_block_height = sync_list[0]
                    received_timestamp = sync_list[1]
                    received_address = sync_list[2]
                    received_to_address = sync_list[3]
                    received_amount = sync_list [4]
                    received_signature = sync_list[5]
                    received_public_key_readable = sync_list[6]
                    received_public_key = RSA.importKey(sync_list[6])
                    received_txhash = sync_list[7]
                    received_transaction = str(received_timestamp) +":"+ str(received_address) +":"+ str(received_to_address) +":"+ str(received_amount) #todo: why not have bare list instead of converting?
                    received_signature_tuple = ast.literal_eval(received_signature) #converting to tuple

                    #txhash validation start

                    #open dbs for mempool backup and followup deletion
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()
                    c.execute("SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1;")
                    txhash_db = c.fetchone()[0]

                    #backup all followups to mempool
                    mempool = sqlite3.connect('mempool.db')
                    m = mempool.cursor()

                    for row in c.execute('SELECT * FROM transactions WHERE block_height > "'+str(received_block_height)+'"'):
                        db_block_height = row[0]
                        db_timestamp = row[1]
                        db_address = row[2]
                        db_to_address = row[3]
                        db_amount = row [4]
                        db_signature = row[5]
                        db_public_key_readable = row[6]
                        db_public_key = RSA.importKey(row[6])
                        db_txhash = row[7]
                        db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount) 

                        m.execute("INSERT INTO transactions VALUES ('"+str(db_block_height)+"','"+str(db_timestamp)+"','"+str(db_address)+"','"+str(db_to_address)+"','"+str(db_amount)+"','"+str(db_signature)+"','"+str(db_public_key_readable)+"','"+str(db_txhash)+"')") # Insert a row of data

                    mempool.commit()
                    mempool.close()
                    #backup all followups to mempool
                    
                    #delete all local followups                   
                    c.execute('DELETE FROM transactions WHERE block_height > "'+str(received_block_height)+'"')
                    conn.close()
                    #delete all local followups
                    
                    print "Last db txhash: "+str(txhash_db)
                    print "Received txhash: "+str(received_txhash)
                    print "Received transaction: "+str(received_transaction)

                    txhash_valid = 0
                    if received_txhash == hashlib.sha224(str(received_transaction) + str(received_signature) +str(txhash_db)).hexdigest(): #new hash = new tx + new sig + old txhash
                        print "txhash valid"
                        txhash_valid = 1

                        #update local db with received tx
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()
                        print "Verifying balance"
                        print "Received address: " +str(received_address)
                        c.execute("SELECT sum(amount) FROM transactions WHERE to_address = '"+received_address+"'")
                        credit = c.fetchone()[0]
                        c.execute("SELECT sum(amount) FROM transactions WHERE address = '"+received_address+"'")
                        debit = c.fetchone()[0]
                        if debit == None:
                            debit = 0
                        if credit == None:
                            credit = 0                                
                        print "Total credit: "+str(credit)                                
                        print "Total debit: "+str(debit)
                        balance = int(credit) - int(debit)
                        print "Transction address balance: "+str(balance)                       
                        conn.close()
                                
                        if  int(balance) - int(received_amount) < 0:
                            print "Their balance is too low for this transaction"
                        elif int(received_amount) < 0:
                            print "Cannot use negative amounts"
                        else:                              
                            #save step to db
                            conn = sqlite3.connect('ledger.db') 
                            c = conn.cursor()
                            c.execute("INSERT INTO transactions VALUES ('"+str(received_block_height)+"','"+str(received_timestamp)+"','"+str(received_address)+"','"+str(received_to_address)+"','"+str(abs(received_amount))+"','"+str(received_signature)+"','"+str(received_public_key_readable)+"','"+str(received_txhash)+"')") # Insert a row of data
                            print "Ledger updated with a received transaction"
                            conn.commit() # Save (commit) the changes
                            conn.close()
                            #save step to db
                        print "Ledger synchronization finished"

                        #digest mempool start
                        while True:                            
                            print "Digesting mempool"
                            mempool = sqlite3.connect('mempool.db')
                            m = mempool.cursor()
                            try:
                                m.execute("SELECT signature FROM transactions ORDER BY block_height DESC LIMIT 1;")
                                signature_mempool = m.fetchone()[0]
                                try:
                                    conn = sqlite3.connect('ledger.db') 
                                    c = conn.cursor()
                                    c.execute("SELECT * FROM transactions WHERE signature ='"+signature_mempool+"';")
                                    txhash_match = c.fetchone()[0]
                                    
                                    print "Mempool tx sig found in the local ledger, deleting tx"
                                    m.execute("DELETE FROM transactions WHERE signature ='"+signature_mempool+"';")
                                    mempool.commit()
    
                                except:
                                    "Mempool tx sig not found in the local ledger, proceeding to insert"

                                    #calculate block height from the ledger
                                    for row in c.execute('SELECT * FROM transactions ORDER BY block_height DESC LIMIT 1;'):
                                        db_block_height = row[0]
                                        db_txhash = row[7]
                                    
                                    for row in m.execute("SELECT * FROM transactions WHERE signature = '"+signature_mempool+"';"):
                                        db_timestamp = row[1]
                                        db_address = row[2]
                                        db_to_address = row[3]
                                        db_amount = row[4]
                                        db_signature = row[5]
                                        db_public_key_readable = row[6]
                                        db_public_key = RSA.importKey(row[6])
                                        db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount)
                                        txhash = hashlib.sha224(str(db_transaction) + str(db_signature) +str(db_txhash)).hexdigest() #calculate txhash from the ledger

                                    c.execute("INSERT INTO transactions VALUES ('"+str(db_block_height+1)+"','"+str(db_timestamp)+"','"+str(db_address)+"','"+str(db_to_address)+"','"+str(db_amount)+"','"+str(db_signature)+"','"+str(db_public_key_readable)+"','"+str(txhash)+"')") # Insert a row of data
                                    conn.commit()
                                    conn.close()                                    
                                
                                    m.execute("DELETE FROM transactions WHERE txhash = '"+db_txhash+"';") #delete tx from mempool now that it is in the ledger
                                    mempool.commit()                                    
                                    mempool.close()
                                    #raise #testing purposes
                                    
                            except:
                                print "Mempool digestion complete, mempool empty"
                                #raise #testing purposes
                                break
                            #digest mempool end

                        self.request.sendall("sync_______")
                        time.sleep(0.1)
                        #update local db with received tx


                        
                    else:
                        print "txhash invalid"
                        #rollback start
                        print "Received invalid txhash"
                        #rollback end

                if data == "blockheight":
                    subdata = self.request.recv(11) #receive client's last block height
                    received_block_height = subdata
                    print "Received block height: "+(received_block_height) +"\n"                    
                    #send own block height
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()                    
                    c.execute('SELECT block_height FROM transactions ORDER BY block_height DESC LIMIT 1')
                    db_block_height = c.fetchone()[0]
                    conn.close()

                    #append zeroes to get static length
                    while len(str(db_block_height)) != 11:
                        db_block_height = "0"+str(db_block_height)
                    self.request.sendall(db_block_height)
                    time.sleep(0.1)
                    #send own block height
                    
                    if received_block_height > db_block_height:
                        print "Client has higher block, receiving"
                        update_me = 1
                        #todo
                        
                    if received_block_height <= db_block_height:
                        print "We have a higher or equal block, hash will be verified"
                        update_me = 0

                    if received_block_height == db_block_height:
                        print "We have the same block height, hash will be verified"
                        update_me = 0

                    if update_me == 1:
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()                
                        c.execute('SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1')
                        db_txhash = c.fetchone()[0] #get latest txhash
                        conn.close()
                        print "txhash to send: " +str(db_txhash)
                        self.request.sendall("mytxhash__")
                        time.sleep(0.1)
                        self.request.sendall(db_txhash) #send latest txhash
                        time.sleep(0.1)

                    if update_me == 0: #update them if update_me is 0
                        data = self.request.recv(56) #receive client's last txhash
                        #send all our followup hashes
                        print "Will seek the following block: " + str(data)
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()

                        c.execute("SELECT * FROM transactions WHERE txhash='"+data+"'")
                        try:
                            txhash_client_block = c.fetchone()[0]

                            print "Client is at block "+str(txhash_client_block) #now check if we have any newer

                            c.execute('SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1')
                            db_txhash = c.fetchone()[0] #get latest txhash
                            if db_txhash == data:
                                print "Client has the latest block"
                                self.request.sendall("nonewblocks")
                                time.sleep(0.1)
             
                            else:
                                c.execute("SELECT * FROM transactions WHERE block_height='"+str(int(txhash_client_block) + 1)+"'") #select incoming transaction + 1
                                txhash_send = c.fetchone()

                                print "Selected "+str(txhash_send)+" to send"
                                
                                conn.close()
                                self.request.sendall("blockfound_")
                                time.sleep(0.1)
                                self.request.sendall(str(txhash_send))
                                time.sleep(0.1)
                            
                        except:
                            print "Block not found"
                            self.request.sendall("blocknotfoun")
                            time.sleep(0.1)
                            #todo send previous

                if data == "blocknotfou":
                    print "Node didn't find the block, deleting latest entry"
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()
                    c.execute('SELECT block_height FROM transactions ORDER BY block_height DESC LIMIT 1')
                    db_block_height = c.fetchone()[0]


                    #backup all followups to mempool
                    mempool = sqlite3.connect('mempool.db')
                    m = mempool.cursor()

                    c.execute('SELECT * FROM transactions ORDER BY block_height DESC LIMIT 1')
                    results = c.fetchone()
                    db_block_height = results[0]
                    db_timestamp = results[1]
                    db_address = results[2]
                    db_to_address = results[3]
                    db_amount = results[4]
                    db_signature = results[5]
                    db_public_key_readable = results[6]
                    db_public_key = RSA.importKey(results[6])
                    db_txhash = results[7]
                    db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount) 

                    txhash = hashlib.sha224(str(db_transaction) + str(db_signature) +str(db_txhash)).hexdigest() #calculate new txhash from ledger latest tx and the new tx

                    m.execute("INSERT INTO transactions VALUES ('"+str(int(db_block_height)+1)+"','"+str(db_timestamp)+"','"+str(db_address)+"','"+str(db_to_address)+"','"+str(db_amount)+"','"+str(db_signature)+"','"+str(db_public_key_readable)+"','"+str(txhash)+"')") # Insert a row of data

                    mempool.commit()
                    mempool.close()
                    #backup all followups to mempool
                    
                    #delete followups
                    c.execute('DELETE FROM transactions WHERE block_height ="'+str(db_block_height)+'"')
                    conn.commit()
                    conn.close()
                    #delete followups
                    self.request.sendall("sync_______") #experimental
                    time.sleep(0.1)
                    
                   
                            
                #latest local block          
                if data == "transaction":
                    data = self.request.recv(2048)
                    data_split = data.split(";")
                    received_transaction = data_split[0]
                    print "Received transaction: "+received_transaction
                    #split message into values
                    try:
                        received_transaction_split = received_transaction.split(":")#todo receive list
                        received_timestamp = received_transaction_split[0]
                        address = received_transaction_split[1]
                        to_address = received_transaction_split[2]
                        amount = int(received_transaction_split[3])
                    except Exception as e:
                        print "Something wrong with the transaction ("+str(e)+")"
                    #split message into values
                    received_signature = data_split[1] #needs to be converted
                    received_signature_tuple = ast.literal_eval(received_signature) #converting to tuple
                    
                    print "Received signature: "+received_signature
                    received_public_key_readable = data_split[2]
                    print "Received public key: "+received_public_key_readable
                    received_txhash = data_split[3]
                    print "Received txhash: "+received_txhash

                    #convert received strings
                    received_public_key = RSA.importKey(received_public_key_readable)
                    #convert received strings
                    
                    if received_public_key.verify(received_transaction, received_signature_tuple) == True:
                        print "The signature is valid"
                        #transaction processing

                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()
                     
                        #verify balance and blockchain                           
                        print "Verifying balance"
                        print "Address:" +address
                        c.execute("SELECT sum(amount) FROM transactions WHERE to_address = '"+address+"'")
                        credit = c.fetchone()[0]
                        c.execute("SELECT sum(amount) FROM transactions WHERE address = '"+address+"'")
                        debit = c.fetchone()[0]
                        if debit == None:
                            debit = 0
                        if credit == None:
                            credit = 0                                
                        print "Total credit: "+str(credit)                                
                        print "Total debit: "+str(debit)
                        balance = int(credit) - int(debit)
                        print "Your balance: "+str(balance) 

                        if  int(balance) - int(amount) < 0:
                            print "Your balance is too low for this transaction"
                        elif int(amount) < 0:
                            print "Cannot use negative amounts"                            
                        else:
                            print "Processing transaction"

                            c.execute('SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1')
                            txhash = c.fetchone()[0]
                            c.execute('SELECT block_height FROM transactions ORDER BY block_height DESC LIMIT 1')
                            block_height = c.fetchone()[0]
                            print "Current latest txhash: "+str(txhash)
                            print "Current top block: " +str(block_height)
                            block_height_new = block_height + 1
                            
                            

                            if received_txhash == hashlib.sha224(str(received_transaction) + str(received_signature) +str(txhash)).hexdigest(): #new hash = new tx + new sig + old txhash
                                print "txhash valid"
                                txhash_valid = 1
                                
                                c.execute("INSERT INTO transactions VALUES ('"+str(block_height_new)+"','"+str(received_timestamp)+"','"+str(address)+"','"+str(to_address)+"','"+str(amount)+"','"+str(received_signature)+"','"+str(received_public_key_readable)+"','"+str(received_txhash)+"')") # Insert a row of data                    
                                #execute transaction                                
                                conn.commit() # Save (commit) the changes
                                #todo: broadcast
                                print "Saved"

                                conn.close()
                                print "Database closed"
                                self.request.sendall("sync_______")
                                time.sleep(0.1)
                                        
                                #transaction processing                        
                                
                            else:
                                print "txhash invalid"
                                conn.close()
                                                            
                            #verify balance and blockchain                            
                                #execute transaction
                            

                    else:
                        print "Signature invalid"

            except: #forcibly closed connection
                print "Lost connection"
                raise #for test purposes only
                break                        

#client thread
def worker():
    while True:
        if os.path.isfile("keys.pem") is True:
            print "keys.pem found"

        else:   
            #generate key pair and an address
            random_generator = Random.new().read
            key = RSA.generate(1024, random_generator)
            public_key = key.publickey()

            private_key_readable = str(key.exportKey())
            public_key_readable = str(key.publickey().exportKey())
            address = hashlib.sha224(public_key_readable).hexdigest() #hashed public key
            #generate key pair and an address

            print "Your address: "+ str(address)
            print "Your private key:\n "+ str(private_key_readable)
            print "Your public key:\n "+ str(public_key_readable)

            pem_file = open("keys.pem", 'a')
            pem_file.write(str(private_key_readable)+"\n"+str(public_key_readable) + "\n\n")
            pem_file.close()
            address_file = open ("address.txt", 'a')
            address_file.write(str(address)+"\n")
            address_file.close()

        # import keys
        key_file = open('keys.pem','r')
        key = RSA.importKey(key_file.read())
        public_key = key.publickey()
        private_key_readable = str(key.exportKey())
        public_key_readable = str(key.publickey().exportKey())
        address = hashlib.sha224(public_key_readable).hexdigest()

        print "Your address: "+ str(address)
        #print "Your private key:\n "+ str(private_key_readable)
        #print "Your public key:\n "+ str(public_key_readable)
        # import keys


        #open peerlist and connect
        with open ("peers.txt", "r") as peer_list:
            peers=peer_list.read()
            peer_tuples = re.findall ("'([\d\.]+)', '([\d]+)'",peers)
            print peer_tuples

        for tuple in peer_tuples:
            HOST = tuple[0]
            #print HOST
            PORT = int(tuple[1])
            #print PORT

         
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #s.settimeout(1)
            s.connect((HOST, PORT))
            print "Connected to "+str(HOST)+" "+str(PORT)
            #network client program

            first_run=1
            while True:
                #communication starter   
                if first_run==1:
                    first_run=0
                    s.sendall('helloserver')
                    time.sleep(0.1)
                    peer = s.getpeername()
                
                #communication starter

                data = s.recv(11) #receive data, one and the only root point
                print 'Received data from '+ str(peer) +"\n"+ str(data)   
                    
                if data == "peers______":
                    subdata = s.recv(2048) #peers are larger 
                    #get remote peers into tuples
                    server_peer_tuples = re.findall ("'([\d\.]+)', '([\d]+)'",subdata)
                    print server_peer_tuples
                    print len(server_peer_tuples)
                    #get remote peers into tuples

                    #get local peers into tuples
                    peer_file = open("peers.txt", 'r')
                    peer_tuples = []
                    for line in peer_file:
                        extension = re.findall ("'([\d\.]+)', '([\d]+)'",line)
                        peer_tuples.extend(extension)
                    peer_file.close()
                    print peer_tuples
                    #get local peers into tuples

                    for x in server_peer_tuples:
                        if x not in peer_tuples:
                            print str(x)+" is a new peer, saving."

                            peer_list_file = open("peers.txt", 'a')
                            peer_list_file.write(str(x)+"\n")
                            peer_list_file.close()        
                            
                        else:
                            print str(x)+" is not a new peer, skipping."


                if data == "mytxhash__":
                        data = s.recv(56) #receive client's last txhash
                        #send all our followup hashes
                        print "Will seek the following block: " + str(data)
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()

                        c.execute("SELECT * FROM transactions WHERE txhash='"+data+"'")
                        try:
                            txhash_client_block = c.fetchone()[0]

                            print "Client is at block "+str(txhash_client_block) #now check if we have any newer

                            c.execute('SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1')
                            db_txhash = c.fetchone()[0] #get latest txhash
                            if db_txhash == data:
                                print "Client has the latest block"
                                s.sendall("nonewblocks")
                                time.sleep(0.1)
             
                            else:
                                c.execute("SELECT * FROM transactions WHERE block_height='"+str(int(txhash_client_block) + 1)+"'") #select incoming transaction + 1
                                txhash_send = c.fetchone()

                                print "Selected "+str(txhash_send)+" to send"
                                
                                conn.close()
                                s.sendall("blockfound_")
                                time.sleep(0.1)
                                s.sendall(str(txhash_send))
                                time.sleep(0.1)
                            
                        except:
                            print "Block not found"
                            s.sendall("blocknotfoun")
                            time.sleep(0.1)                    
                    
                if data == "sync_______":            
                    #sync start

                    #send block height, receive block height
                    s.sendall("blockheight")
                    time.sleep(0.1)
                    
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()            
                    c.execute('SELECT block_height FROM transactions ORDER BY block_height DESC LIMIT 1')
                    db_block_height = c.fetchone()[0]
                    conn.close()
                    
                    print "Sending block height to compare: "+str(db_block_height)
                    #append zeroes to get static length
                    while len(str(db_block_height)) != 11:
                        db_block_height = "0"+str(db_block_height)
                    s.sendall(str(db_block_height))
                    time.sleep(0.1)
                    
                    subdata = s.recv(11) #receive node's block height
                    received_block_height = subdata
                    print "Node is at block height: "+str(received_block_height)+"\n"

                    if received_block_height < db_block_height:
                        print "We have a higher or equal block, sending"
                        update_me = 0
                        #todo
                    
                    if received_block_height > db_block_height:
                        print "Node has higher block, receiving"
                        update_me = 1
                        #todo

                    if received_block_height == db_block_height:
                        print "We have the same block height, hash will be verified"
                        update_me = 1
                        #todo                

                    if update_me == 1:                
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()                
                        c.execute('SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1')
                        db_txhash = c.fetchone()[0] #get latest txhash
                        conn.close()
                        print "txhash to send: " +str(db_txhash)
                        
                        s.sendall(db_txhash) #send latest txhash
                        time.sleep(0.1)
                           
                if data == "blocknotfou":
                    print "Node didn't find the block, deleting latest entry"
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()
                    c.execute('SELECT block_height FROM transactions ORDER BY block_height DESC LIMIT 1')
                    db_block_height = c.fetchone()[0]

                    #backup all followups to mempool
                    mempool = sqlite3.connect('mempool.db')
                    m = mempool.cursor()

                    c.execute('SELECT * FROM transactions ORDER BY block_height DESC LIMIT 1')
                    results = c.fetchone()
                    db_block_height = results[0]
                    db_timestamp = results[1]
                    db_address = results[2]
                    db_to_address = results[3]
                    db_amount = results[4]
                    db_signature = results[5]
                    db_public_key_readable = results[6]
                    db_public_key = RSA.importKey(results[6])
                    db_txhash = results[7]
                    db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount) 

                    m.execute("INSERT INTO transactions VALUES ('"+str(db_block_height)+"','"+str(db_timestamp)+"','"+str(db_address)+"','"+str(db_to_address)+"','"+str(db_amount)+"','"+str(db_signature)+"','"+str(db_public_key_readable)+"','"+str(db_txhash)+"')") # Insert a row of data

                    mempool.commit()
                    mempool.close()
                    #backup all followups to mempool
                    
                    #delete followups
                    c.execute('DELETE FROM transactions WHERE block_height ="'+str(db_block_height)+'"')
                    conn.commit()
                    conn.close()
                    #delete followups
                    s.sendall("helloserver") #experimental 
                           
                if data == "blockfound_":          
                    print "Node has the block" #node should start sending txs in this step
                    #todo critical: make sure that received block height is correct
                    data = s.recv(2048)
                    print data +"\n"
                    #verify
                    sync_list = ast.literal_eval(data) #this is great, need to add it to client -> node sync
                    received_block_height = sync_list[0]
                    received_timestamp = sync_list[1]
                    received_address = sync_list[2]
                    received_to_address = sync_list[3]
                    received_amount = sync_list [4]
                    received_signature = sync_list[5]
                    received_public_key_readable = sync_list[6]
                    received_public_key = RSA.importKey(sync_list[6])
                    received_txhash = sync_list[7]
                    received_transaction = str(received_timestamp) +":"+ str(received_address) +":"+ str(received_to_address) +":"+ str(received_amount) #todo: why not have bare list instead of converting?
                    received_signature_tuple = ast.literal_eval(received_signature) #converting to tuple

                    #txhash validation start

                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()
                    c.execute("SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1;")
                    txhash_db = c.fetchone()[0]
                    
                    #backup all followups to mempool
                    mempool = sqlite3.connect('mempool.db')
                    m = mempool.cursor()

                    for row in c.execute('SELECT * FROM transactions WHERE block_height > "'+str(received_block_height)+'"'):
                        db_block_height = row[0]
                        db_timestamp = row[1]
                        db_address = row[2]
                        db_to_address = row[3]
                        db_amount = row [4]
                        db_signature = row[5]
                        db_public_key_readable = row[6]
                        db_public_key = RSA.importKey(row[6])
                        db_txhash = row[7]
                        db_transaction = str(db_timestamp) +":"+ str(db_address) +":"+ str(db_to_address) +":"+ str(db_amount) 

                        m.execute("INSERT INTO transactions VALUES ('"+str(db_block_height)+"','"+str(db_timestamp)+"','"+str(db_address)+"','"+str(db_to_address)+"','"+str(db_amount)+"','"+str(db_signature)+"','"+str(db_public_key_readable)+"','"+str(db_txhash)+"')") # Insert a row of data

                    mempool.commit()
                    mempool.close()
                    #backup all followups to mempool       
                    
                    #delete all local followups
                    c.execute('DELETE FROM transactions WHERE block_height > "'+str(received_block_height)+'"')
                    conn.close()
                    #delete all local followups
                    
                    print "Last db txhash: "+str(txhash_db)
                    print "Received txhash: "+str(received_txhash)
                    print "Received transaction: "+str(received_transaction)

                    txhash_valid = 0
                    if received_txhash == hashlib.sha224(str(received_transaction) + str(received_signature) +str(txhash_db)).hexdigest(): #new hash = new tx + new sig + old txhash
                        print "txhash valid"
                        txhash_valid = 1

                        #update local db with received tx
                        conn = sqlite3.connect('ledger.db')
                        c = conn.cursor()
                        print "Verifying balance"
                        print "Received address: " +str(received_address)
                        c.execute("SELECT sum(amount) FROM transactions WHERE to_address = '"+received_address+"'")
                        credit = c.fetchone()[0]
                        c.execute("SELECT sum(amount) FROM transactions WHERE address = '"+received_address+"'")
                        debit = c.fetchone()[0]
                        if debit == None:
                            debit = 0
                        if credit == None:
                            credit = 0                                
                        print "Total credit: "+str(credit)                                
                        print "Total debit: "+str(debit)
                        balance = int(credit) - int(debit)
                        print "Transction address balance: "+str(balance)                       
                        conn.close()
                                
                        if  int(balance) - int(received_amount) < 0:
                            print "Their balance is too low for this transaction"
                        elif int(received_amount) < 0:
                            print "Cannot use negative amounts"
                        else:                              
                            #save step to db
                            conn = sqlite3.connect('ledger.db') 
                            c = conn.cursor()
                            c.execute("INSERT INTO transactions VALUES ('"+str(received_block_height)+"','"+str(received_timestamp)+"','"+str(received_address)+"','"+str(received_to_address)+"','"+str(received_amount)+"','"+str(received_signature)+"','"+str(received_public_key_readable)+"','"+str(received_txhash)+"')") # Insert a row of data
                            print "Ledger updated with a received transaction"
                            conn.commit() # Save (commit) the changes
                            conn.close()
                            #save step to db
                        print "Ledger synchronization finished"
                        #s.sendall("Sync finished")
                        #update local db with received tx                    

                    else:
                        print "txhash invalid"
                        #rollback start
                        print "Received invalid txhash"
                        #rollback end
                                
                    #txhash validation end

                if data == "nonewblocks":
                    print "We seem to be at the latest block"

                    #enter transaction start
                    conn = sqlite3.connect('ledger.db')
                    c = conn.cursor()
                    c.execute("SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1;")
                    txhash = c.fetchone()[0]
                    conn.close()
                        
                    to_address = str(raw_input ("Send to address: "))
                    amount = str(raw_input ("How much to send: "))

                    timestamp = str(time.time())
                    transaction = str(timestamp) +":"+ str(address) +":"+ str(to_address) +":"+ str(amount)
                    signature = key.sign(transaction, '')
                    print "Signature: "+str(signature)

                    if public_key.verify(transaction, signature) == True:
                        if int(amount) < 0:
                            print "Signature OK, but cannot use negative amounts"

                        else:
                            conn = sqlite3.connect('ledger.db')
                            c = conn.cursor()
                            c.execute("SELECT txhash FROM transactions ORDER BY block_height DESC LIMIT 1;")
                            txhash = str(c.fetchone()[0])
                            txhash_new = hashlib.sha224(str(transaction) + str(signature) + str(txhash)).hexdigest() #define new tx hash based on previous #fix asap
                            print "New txhash to go with your transaction: "+txhash_new
                            conn.close()
                               
                            print "The signature and control txhash is valid, proceeding to send transaction, signature, new txhash and the public key"
                            s.sendall("transaction")
                            time.sleep(0.1)
                            s.sendall(transaction+";"+str(signature)+";"+public_key_readable+";"+str(txhash_new)) #todo send list
                            time.sleep(0.1)
                        
                    else:
                        print "Invalid signature"
                    #enter transaction end
    return

t = threading.Thread(target=worker)
t.start()

#client thread


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass
    

if __name__ == "__main__":
    # Port 0 means to select an arbitrary unused port
    HOST, PORT = "localhost", port

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    ip, port = server.server_address

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates    
    
    server_thread.daemon = True
    server_thread.start()
    print "Server loop running in thread:", server_thread.name
    server.serve_forever() #added
    server.shutdown()
    server.server_close()

